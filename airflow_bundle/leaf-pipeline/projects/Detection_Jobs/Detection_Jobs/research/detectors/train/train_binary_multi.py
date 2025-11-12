# agri-baseline/src/detectors/train_binary_multi.py
import argparse
import os
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import datasets, transforms
from torch.optim.lr_scheduler import ReduceLROnPlateau
import numpy as np

from ...agri_baseline.src.detectors.cnn_binary_classifier import build_binary_model
from ...agri_baseline.src.detectors.cnn_multi_classifier import build_multi_model
from ...agri_baseline.src.detectors.dataset_binary import BinaryDiseaseDataset


def train_model(model, dataloader, val_dl, device, epochs, lr, out_path):
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.CrossEntropyLoss()
    scheduler = ReduceLROnPlateau(opt, mode="min", factor=0.5, patience=3, verbose=True)

    best_val_loss = float("inf")
    patience, counter = 5, 0

    for epoch in range(epochs):
        model.train()
        running_loss, correct, total = 0.0, 0, 0
        for batch in dataloader:
            if len(batch) == 3:
                xb, yb, _ = batch
            else:
                xb, yb = batch
            xb, yb = xb.to(device), yb.to(device)

            opt.zero_grad()
            preds = model(xb)
            loss = loss_fn(preds, yb)
            loss.backward()
            opt.step()

            running_loss += loss.item() * xb.size(0)
            _, predicted = preds.max(1)
            correct += predicted.eq(yb).sum().item()
            total += yb.size(0)

        acc = correct / total

        # Validation
        val_loss, val_acc = evaluate(model, val_dl, device, loss_fn)
        print(f"Epoch {epoch+1}/{epochs} "
              f"Train Loss={running_loss/total:.4f} Train Acc={acc:.3f} "
              f"Val Loss={val_loss:.4f} Val Acc={val_acc:.3f}")

        scheduler.step(val_loss)

        # EarlyStopping
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            counter = 0
            torch.save(model.state_dict(), out_path)
            print(f"💾 Saved best model {out_path}")
        else:
            counter += 1
            print(f"⏳ EarlyStopping counter {counter}/{patience}")
            if counter >= patience:
                print("🛑 Early stopping triggered")
                break


def evaluate(model, dataloader, device, loss_fn):
    model.eval()
    correct, total, total_loss = 0, 0, 0.0
    with torch.no_grad():
        for batch in dataloader:
            if len(batch) == 3:
                xb, yb, _ = batch
            else:
                xb, yb = batch
            xb, yb = xb.to(device), yb.to(device)
            preds = model(xb)
            loss = loss_fn(preds, yb)
            total_loss += loss.item() * xb.size(0)
            _, predicted = preds.max(1)
            correct += predicted.eq(yb).sum().item()
            total += yb.size(0)
    return total_loss/total, correct/total


def make_sampler(targets):
    class_counts = np.bincount(targets)
    class_weights = 1. / class_counts
    sample_weights = [class_weights[t] for t in targets]
    return WeightedRandomSampler(weights=sample_weights,
                                 num_samples=len(sample_weights),
                                 replacement=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True, help="Dataset root (with train/val/test)")
    p.add_argument("--out", default="./models")
    p.add_argument("--epochs", type=int, default=10)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--device", default="cpu")
    args = p.parse_args()

    device = torch.device(args.device)

    # Augmentations
    train_tfms = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.8, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
    ])
    test_tfms = transforms.Compose([
        transforms.Resize((224,224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
    ])

    # Binary dataset
    train_bin = BinaryDiseaseDataset(os.path.join(args.data,"train"), transform=train_tfms)
    val_bin   = BinaryDiseaseDataset(os.path.join(args.data,"val"), transform=test_tfms)

    sampler_bin = make_sampler(train_bin.targets)
    train_dl_bin = DataLoader(train_bin, batch_size=args.batch, sampler=sampler_bin)
    val_dl_bin   = DataLoader(val_bin, batch_size=args.batch)

    model_bin = build_binary_model().to(device)
    train_model(model_bin, train_dl_bin, val_dl_bin, device, args.epochs, args.lr,
                os.path.join(args.out, "cnn_binary.pth"))

    # Multi-class dataset
    train_multi = datasets.ImageFolder(os.path.join(args.data,"train"), transform=train_tfms)
    val_multi   = datasets.ImageFolder(os.path.join(args.data,"val"), transform=test_tfms)

    sampler_multi = make_sampler([y for _, y in train_multi.samples])
    train_dl_multi = DataLoader(train_multi, batch_size=args.batch, sampler=sampler_multi)
    val_dl_multi   = DataLoader(val_multi, batch_size=args.batch)

    model_multi = build_multi_model(num_classes=len(train_multi.classes)).to(device)
    train_model(model_multi, train_dl_multi, val_dl_multi, device, args.epochs, args.lr,
                os.path.join(args.out, "cnn_multi.pth"))

    torch.save({"classes": train_multi.classes},
               os.path.join(args.out,"multi_classes.pth"))

if __name__=="__main__":
    main()
