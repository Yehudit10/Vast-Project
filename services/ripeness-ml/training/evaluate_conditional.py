# -*- coding: utf-8 -*-
# Evaluate the conditional ripeness model on test/val CSVs.
# Outputs:
#  - metrics.json (accuracy, macro_f1, per-class F1)
#  - classification_report.txt
#  - confusion_matrix.png

import os, sys, json, yaml
from pathlib import Path
import numpy as np
import torch
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix
import matplotlib.pyplot as plt

# --- make 'models' & 'training' importable when running as a script ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from models.mobilenet_v3_large_head import build_conditional
from training.data_multitask import CSVConditional, build_transforms

IMAGENET_MEAN=(0.485,0.456,0.406)
IMAGENET_STD=(0.229,0.224,0.225)

def softmax(x):
    x = x - x.max(axis=1, keepdims=True)
    e = np.exp(x)
    return e / e.sum(axis=1, keepdims=True)

def load_cfg():
    return yaml.safe_load(open(os.path.join(PROJECT_ROOT, "configs/config.yaml"), "r", encoding="utf-8"))

def make_loader(csv_path, fruits, ripeness, img_size=224, batch_size=64, num_workers=0):
    _, t_val = build_transforms(img_size)
    f2i = {f:i for i,f in enumerate(fruits)}
    r2i = {r:i for i,r in enumerate(ripeness)}
    ds  = CSVConditional(csv_path, f2i, r2i, transform=t_val)
    from torch.utils.data import DataLoader
    return DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=num_workers, pin_memory=True)

def plot_confusion_matrix(cm, classes, out_png):
    fig = plt.figure(figsize=(5.5, 4.5))
    ax = fig.add_subplot(111)
    im = ax.imshow(cm, interpolation='nearest')
    ax.set_title('Confusion Matrix')
    fig.colorbar(im)
    tick_marks = np.arange(len(classes))
    ax.set_xticks(tick_marks); ax.set_xticklabels(classes, rotation=45, ha="right")
    ax.set_yticks(tick_marks); ax.set_yticklabels(classes)
    ax.set_ylabel('True'); ax.set_xlabel('Predicted')
    # write counts
    thresh = cm.max() / 2.0 if cm.size else 0.5
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, format(cm[i, j], 'd'),
                    ha="center", va="center",
                    color="white" if cm[i, j] > thresh else "black")
    fig.tight_layout()
    fig.savefig(out_png, dpi=160)
    plt.close(fig)

if __name__ == "__main__":
    cfg = load_cfg()
    device = "cuda" if torch.cuda.is_available() else "cpu"

    fruits   = cfg["fruits"]
    ripeness = cfg["ripeness"]

    # choose CSV: prefer test.csv; if missing/empty -> use val.csv
    csv_test = Path(cfg["csv"].get("test", "data_mt/test.csv"))
    csv_val  = Path(cfg["csv"].get("val",  "data_mt/val.csv"))
    csv_path = csv_test if csv_test.exists() and csv_test.stat().st_size > 50 else csv_val
    if not csv_path.exists():
        raise SystemExit(f"CSV not found: {csv_path}. Run ingest to create it.")

    # dataloader
    loader = make_loader(
        str(csv_path), fruits, ripeness,
        img_size=cfg.get("img_size", 224),
        batch_size=cfg.get("batch_size", 32),
        num_workers=cfg.get("num_workers", 0)  
    )

    # model
    ckpt_dir = cfg["checkpoint_dir"]
    ckpt = os.path.join(ckpt_dir, "best_conditional.pt")
    if not os.path.exists(ckpt):
        raise SystemExit(f"Checkpoint not found: {ckpt}")

    model = build_conditional(num_ripeness=len(ripeness), num_fruits=len(fruits))
    model.load_state_dict(torch.load(ckpt, map_location="cpu"))
    model.eval().to(device)

    # predict
    y_true, y_pred = [], []
    probs_all = []
    with torch.no_grad():
        for x, fidx, ridx in loader:
            x = x.to(device)
            fidx = torch.as_tensor(fidx, device=device)
            logits = model(x, fidx).cpu().numpy()
            prob = softmax(logits)
            preds = prob.argmax(1)
            y_pred.extend(preds.tolist())
            y_true.extend(ridx.numpy().tolist())
            probs_all.append(prob)

    y_true = np.array(y_true)
    y_pred = np.array(y_pred)
    probs  = np.concatenate(probs_all, axis=0) if probs_all else np.empty((0,len(ripeness)))

    # metrics
    acc = float(accuracy_score(y_true, y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro"))
    per_class_f1 = f1_score(y_true, y_pred, average=None)
    per_class = {ripeness[i]: float(per_class_f1[i]) for i in range(len(ripeness))}
    report = classification_report(y_true, y_pred, target_names=ripeness, digits=4)
    cm = confusion_matrix(y_true, y_pred)

    # outputs
    out_dir = os.path.join(PROJECT_ROOT, "checkpoints", "eval")
    os.makedirs(out_dir, exist_ok=True)
    # confusion matrix PNG
    cm_png = os.path.join(out_dir, "confusion_matrix.png")
    plot_confusion_matrix(cm, ripeness, cm_png)
    # classification report
    with open(os.path.join(out_dir, "classification_report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")
        f.write(f"\nAccuracy: {acc:.4f}\nMacro-F1: {macro_f1:.4f}\n")
    # json metrics
    with open(os.path.join(out_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump({"accuracy": acc, "macro_f1": macro_f1, "per_class_f1": per_class}, f, indent=2)

    print(f"Evaluated on: {csv_path}")
    print(f"Accuracy: {acc:.4f} | Macro-F1: {macro_f1:.4f}")
    print("Per-class F1:", per_class)
    print(f"Saved: {cm_png} and classification_report.txt, metrics.json")
