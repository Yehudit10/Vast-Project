"""
Train a small classifier to refine weed mask using pseudo-labels (heuristic or GT).
Saves weights to WEIGHTS_OUT (default: ./weights_refiner.pth).

Usage:
  python -m src.train_ml_refiner
Env (.env):
  INPUT_DIR=...       # same as batch
  GT_DIR=...          # optional, if you have GT
  USE_GT=0/1          # 1 to use GT masks if available
  EPOCHS=3
  BATCH_SIZE=64
  LR=1e-3
  WEIGHTS_OUT=./weights_refiner.pth
  SAMPLES_PER_IMAGE=64
  LIMIT_IMAGES=0      # 0 = no limit
  MAX_STEPS_PER_EPOCH=0  # 0 = no limit
"""

import os
from dotenv import load_dotenv
import torch
from torch.utils.data import DataLoader, random_split
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm

from .data_ml import PatchRefineDataset
from .ml_model import WeedNet  # mobilenet_v3_small head -> 2 classes


def main():
    load_dotenv()
    images_dir = os.getenv("INPUT_DIR", "./data/images")
    gt_dir     = os.getenv("GT_DIR", "./data/labels")
    use_gt     = os.getenv("USE_GT", "0") == "1"
    epochs     = int(os.getenv("EPOCHS", "3"))
    bs         = int(os.getenv("BATCH_SIZE", "64"))
    lr         = float(os.getenv("LR", "1e-3"))
    weights_out= os.getenv("WEIGHTS_OUT", "./weights_refiner.pth")

    samples_per_image = int(os.getenv("SAMPLES_PER_IMAGE", "64"))
    limit_images      = int(os.getenv("LIMIT_IMAGES", "0"))
    max_steps_per_epoch = int(os.getenv("MAX_STEPS_PER_EPOCH", "0"))

    # Load dataset
    ds = PatchRefineDataset(images_dir, gt_dir, use_gt=use_gt,
                            samples_per_image=samples_per_image, patch_radius=16)

    if limit_images > 0:
        ds.images = ds.images[:limit_images]

    n = len(ds)
    n_train = int(0.9 * n)
    n_val = n - n_train
    train_ds, val_ds = random_split(ds, [n_train, n_val])

    train_loader = DataLoader(train_ds, batch_size=bs, shuffle=True, num_workers=0, pin_memory=True)
    val_loader   = DataLoader(val_ds, batch_size=bs, shuffle=False, num_workers=0, pin_memory=True)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = WeedNet(num_classes=2).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    best_acc = 0.0
    for epoch in range(1, epochs+1):
        model.train()
        total = correct = 0
        pbar = tqdm(train_loader, desc=f"Train {epoch}/{epochs}")
        for step, (x, y) in enumerate(pbar, start=1):
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            logits = model(x)
            loss = criterion(logits, y)
            loss.backward()
            optimizer.step()
            pred = logits.argmax(1)
            correct += (pred == y).sum().item()
            total += y.numel()
            pbar.set_postfix(loss=f"{loss.item():.4f}", acc=f"{(correct/total)*100:.1f}%")

            if max_steps_per_epoch and step >= max_steps_per_epoch:
                break

        # validation
        model.eval()
        v_total = v_correct = 0
        with torch.no_grad():
            for x, y in val_loader:
                x, y = x.to(device), y.to(device)
                logits = model(x)
                pred = logits.argmax(1)
                v_correct += (pred == y).sum().item()
                v_total += y.numel()
        v_acc = v_correct / max(1, v_total)
        if v_acc > best_acc:
            best_acc = v_acc
            torch.save(model.state_dict(), weights_out)

        print(f"[VAL] acc={v_acc:.4f} (best={best_acc:.4f})")

    print(f"[DONE] Saved best weights to: {weights_out}")


if __name__ == "__main__":
    main()
