import os, yaml, torch
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from sklearn.metrics import accuracy_score, f1_score

from models.mobilenet_v3_large_head import build_conditional
from .data_multitask import make_loaders

def evaluate(model, loader, device):
    model.eval()
    y_true, y_pred = [], []
    with torch.no_grad():
        for x, fidx, ridx in loader:
            x = x.to(device)
            fidx = torch.as_tensor(fidx, device=device)
            logits = model(x, fidx)
            y_pred.extend(logits.argmax(1).cpu().numpy())
            y_true.extend(ridx.numpy())
    acc = accuracy_score(y_true, y_pred)
    f1  = f1_score(y_true, y_pred, average="macro")
    return acc, f1

if __name__ == "__main__":
    cfg = yaml.safe_load(open("configs/config.yaml"))
    device = "cuda" if torch.cuda.is_available() else "cpu"

    train_csv = cfg["csv"]["train"]; val_csv = cfg["csv"]["val"]
    fruits    = cfg["fruits"]; ripeness = cfg["ripeness"]

    ltr, lva, f2i, r2i = make_loaders(
        train_csv, val_csv,
        cfg["img_size"], cfg["batch_size"], cfg["num_workers"],
        fruits, ripeness
    )

    model = build_conditional(num_ripeness=len(ripeness), num_fruits=len(fruits)).to(device)

    # Phase 1: freeze backbone
    for p in model.backbone.features.parameters(): p.requires_grad=False

    ce = nn.CrossEntropyLoss()
    def train_phase(epochs, lr, wd):
        opt = AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr, weight_decay=wd)
        sch = CosineAnnealingLR(opt, T_max=epochs)
        best, best_state = -1, None
        for ep in range(1, epochs+1):
            model.train()
            for x, fidx, ridx in ltr:
                x = x.to(device)
                fidx = torch.as_tensor(fidx, device=device)
                ridx = torch.as_tensor(ridx, device=device)
                logits = model(x, fidx)
                loss = ce(logits, ridx)
                opt.zero_grad(); loss.backward(); opt.step()
            acc, f1 = evaluate(model, lva, device); sch.step()
            print(f"[Epoch {ep}] val_acc={acc:.3f} val_f1={f1:.3f}")
            if f1 > best:
                best, best_state = f1, {k:v.cpu() for k,v in model.state_dict().items()}
        model.load_state_dict(best_state)

    train_phase(cfg["epochs_frozen"], cfg["lr"], cfg["weight_decay"])
    for p in model.parameters(): p.requires_grad=True
    train_phase(cfg["epochs_unfrozen"], cfg["lr"]/3, cfg["weight_decay"])

    os.makedirs(cfg["checkpoint_dir"], exist_ok=True)
    torch.save(model.state_dict(), os.path.join(cfg["checkpoint_dir"], "best_conditional.pt"))
    print("Saved:", os.path.join(cfg["checkpoint_dir"], "best_conditional.pt"))
