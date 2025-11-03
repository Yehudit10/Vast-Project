import os, yaml, torch
from torch import nn
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR
from sklearn.metrics import f1_score, accuracy_score
from models.mobilenet_v3_large_head import build_model
from .data import make_loaders
from .utils import set_seed, load_class_weights

def evaluate(model, loader, device):
    model.eval()
    y_true, y_pred = [], []
    with torch.no_grad():
        for x,y in loader:
            x = x.to(device)
            preds = model(x).argmax(1).cpu().numpy()
            y_pred.extend(preds); y_true.extend(y.numpy())
    acc = accuracy_score(y_true, y_pred)
    f1  = f1_score(y_true, y_pred, average="macro")
    return acc, f1

def train_phase(model, loader, valloader, device, epochs, lr, wd, class_weights=None, label_smoothing=0.0):
    model.to(device)
    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=label_smoothing)
    optim = AdamW(model.parameters(), lr=lr, weight_decay=wd)
    sched = CosineAnnealingLR(optim, T_max=epochs)
    best_f1, best_state = -1, None
    for ep in range(1, epochs+1):
        model.train()
        for x,y in loader:
            x,y = x.to(device), y.to(device)
            loss = criterion(model(x), y)
            optim.zero_grad(); loss.backward(); optim.step()
        acc,f1 = evaluate(model, valloader, device); sched.step()
        print(f"[Epoch {ep}] val_acc={acc:.3f} val_f1={f1:.3f}")
        if f1 > best_f1:
            best_f1, best_state = f1, {k:v.cpu() for k,v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return model, best_f1

if __name__ == "__main__":
    cfg = yaml.safe_load(open("configs/config.yaml"))
    set_seed(cfg.get("seed",42))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    trainloader, valloader, classes = make_loaders(cfg["train_dir"], cfg["val_dir"],
                                                   cfg["img_size"], cfg["batch_size"], cfg["num_workers"])
    model = build_model(num_classes=len(classes))
    # Freeze
    for p in model.features.parameters(): p.requires_grad=False
    cw = load_class_weights(trainloader, use=cfg["use_class_weights"])
    model, _ = train_phase(model, trainloader, valloader, device,
                           cfg["epochs_frozen"], cfg["lr"], cfg["weight_decay"],
                           class_weights=cw, label_smoothing=cfg["label_smoothing"])
    # Unfreeze
    for p in model.parameters(): p.requires_grad=True
    model, best_f1 = train_phase(model, trainloader, valloader, device,
                                 cfg["epochs_unfrozen"], cfg["lr"]/3, cfg["weight_decay"],
                                 class_weights=cw, label_smoothing=cfg["label_smoothing"])
    os.makedirs(cfg["checkpoint_dir"], exist_ok=True)
    torch.save(model.state_dict(), os.path.join(cfg["checkpoint_dir"], "best.pt"))
    print("Saved checkpoint:", os.path.join(cfg["checkpoint_dir"], "best.pt"), "| best F1:", best_f1)
