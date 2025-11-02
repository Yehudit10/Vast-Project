# training/train_fruit_defect_cls.py
import os, time, yaml, math, random
from pathlib import Path
from collections import deque
from typing import List

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms, models
from PIL import Image
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from tqdm import tqdm

# ========= Utils =========
IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

def set_seed(seed: int = 42):
    random.seed(seed); torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed); torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

def is_image(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMG_EXTS

def label_from_path(p: Path) -> int:
    parts = [s.lower() for s in p.parts]
    name = " ".join(parts)
    if ("healthy" in name) or ("fresh" in name):
        return 0
    if any(k in name for k in ["rotten", "defect", "bad", "decay", "mold", "mould", "damaged", "spoiled"]):
        return 1
    return 1 if "rotten" in p.parent.name.lower() else 0

# ========= Dataset =========
class BinaryFruitDataset(Dataset):
    def __init__(self, root: str, img_size: int, augment: bool):
        self.root = Path(root)
        self.items: List[Path] = [p for p in self.root.rglob("*") if is_image(p)]
        if not self.items:
            raise RuntimeError(f"No images found under: {root}")
        mean, std = [0.485,0.456,0.406], [0.229,0.224,0.225]
        base = [transforms.Resize((img_size, img_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean, std)]
        if augment:
            aug = [transforms.RandomHorizontalFlip(),
                   transforms.ColorJitter(0.1,0.1,0.1,0.05)]
            self.tf = transforms.Compose(aug + base)
        else:
            self.tf = transforms.Compose(base)

    def __len__(self): return len(self.items)

    def __getitem__(self, idx):
        p = self.items[idx]
        y = label_from_path(p)
        im = Image.open(p).convert("RGB")
        x = self.tf(im)
        return x, y

# ========= Model =========
def build_model(backbone: str):
    backbone = (backbone or "mobilenet_v3_small").lower()
    if "mobile" in backbone:
        try:
            m = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
        except Exception:
            m = models.mobilenet_v3_small()
        m.classifier[-1] = nn.Linear(m.classifier[-1].in_features, 2)
        return m
    else:
        try:
            m = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
        except Exception:
            m = models.resnet18()
        m.fc = nn.Linear(m.fc.in_features, 2)
        return m

@torch.no_grad()
def evaluate(model, dl, device):
    model.eval()
    all_y, all_p = [], []
    for x, y in dl:
        x = x.to(device); y = torch.tensor(y).to(device)
        logits = model(x)
        pred = logits.argmax(1)
        all_y.extend(y.cpu().tolist())
        all_p.extend(pred.cpu().tolist())
    acc = accuracy_score(all_y, all_p)
    p, r, f1, _ = precision_recall_fscore_support(all_y, all_p, average="binary", zero_division=0)
    return {"accuracy": acc, "precision": p, "recall": r, "f1": f1}

# ========= Train =========
def train_one_run(cfg):
    set_seed(42)

    # --- data ---
    img_size = int(cfg["model"]["img_size"])
    bs = int(cfg["train"]["batch_size"])
    train_ds = BinaryFruitDataset(cfg["data"]["train_dir"], img_size, augment=True)
    val_ds   = BinaryFruitDataset(cfg["data"]["val_dir"],   img_size, augment=False)

    train_dl = DataLoader(train_ds, batch_size=bs, shuffle=True,  num_workers=2, pin_memory=True)
    val_dl   = DataLoader(val_ds,   batch_size=bs, shuffle=False, num_workers=2, pin_memory=True)

    # --- model ---
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = build_model(cfg["model"]["backbone"]).to(device)

    # --- optim ---
    lr = float(cfg["train"]["lr"])
    wd = float(cfg["train"]["weight_decay"])
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    loss_fn = nn.CrossEntropyLoss()

    # --- tensorboard (optional) ---
    tb = None
    try:
        from torch.utils.tensorboard import SummaryWriter
        log_dir = Path("outputs/runs"); log_dir.mkdir(parents=True, exist_ok=True)
        tb = SummaryWriter(log_dir=str(log_dir))
    except Exception:
        tb = None

    # --- training loop with live metrics ---
    best_acc, best_state = -1.0, None
    epochs = int(cfg["train"]["epochs"])

    for ep in range(1, epochs+1):
        model.train()
        loss_window, acc_window = deque(maxlen=100), deque(maxlen=100)
        pbar = tqdm(
        train_dl,
        desc=f"epoch {ep}/{epochs}",
        dynamic_ncols=True, 
        mininterval=1.0,    
        smoothing=0.2,    
        leave=False    
    )


        correct_total, seen_total = 0, 0

        for step, (x, y) in enumerate(pbar, start=1):
            x = x.to(device); y = torch.tensor(y).to(device)

            logits = model(x)
            loss = loss_fn(logits, y)

            opt.zero_grad()
            loss.backward()
            opt.step()

            # running metrics (per mini-batch)
            with torch.no_grad():
                preds = logits.argmax(1)
                correct = (preds == y).sum().item()
                batch_acc = correct / y.size(0)

            loss_window.append(float(loss))
            acc_window.append(batch_acc)
            correct_total += correct
            seen_total += y.size(0)

            avg_loss = sum(loss_window)/len(loss_window)
            avg_acc  = 100.0 * (sum(acc_window)/len(acc_window))
            pbar.set_postfix(loss=f"{avg_loss:.4f}",
                             train_acc=f"{avg_acc:.1f}%",
                             lr=f"{opt.param_groups[0]['lr']:.1e}")

            # tensorboard (every ~10 steps)
            if tb and (step % 10 == 0):
                global_step = (ep-1)*len(train_dl) + step
                tb.add_scalar("train/loss", avg_loss, global_step)
                tb.add_scalar("train/acc",  avg_acc/100.0, global_step)
                tb.add_scalar("train/lr",   opt.param_groups[0]['lr'], global_step)

        # epoch-level metrics
        epoch_train_acc = 100.0 * correct_total / max(1, seen_total)
        metrics = evaluate(model, val_dl, device)
        msg = {
            "val_accuracy": round(metrics["accuracy"], 4),
            "val_precision": round(metrics["precision"], 4),
            "val_recall": round(metrics["recall"], 4),
            "val_f1": round(metrics["f1"], 4),
            "train_acc_epoch_%": round(epoch_train_acc, 2)
        }
        print("val metrics:", msg)

        if tb:
            tb.add_scalar("val/accuracy", metrics["accuracy"], ep)
            tb.add_scalar("val/precision", metrics["precision"], ep)
            tb.add_scalar("val/recall", metrics["recall"], ep)
            tb.add_scalar("val/f1", metrics["f1"], ep)

        # keep best by val accuracy
        if metrics["accuracy"] > best_acc:
            best_acc = metrics["accuracy"]
            best_state = {k: v.detach().cpu() for k, v in model.state_dict().items()}

    # --- save best weights ---
    out = Path(cfg["paths"]["best_weights"])
    out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, out)
    print(f"saved best weights: {out}  best_val_acc={round(best_acc,4)}")

def main():
    cfg = yaml.safe_load(open("configs/fruit_defect.yaml", "r", encoding="utf-8"))
    train_one_run(cfg)

if __name__ == "__main__":
    main()
