import argparse, os, json
from pathlib import Path
import numpy as np
from PIL import Image
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models
from tqdm import tqdm

def build_dataloaders(train_dir, val_dir, batch_size):
    aug = transforms.Compose([
        transforms.RandomResizedCrop(224, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.ToTensor()
    ])
    val_tf = transforms.Compose([
        transforms.Resize((224,224)),
        transforms.ToTensor()
    ])
    train_ds = datasets.ImageFolder(train_dir, transform=aug)
    val_ds = datasets.ImageFolder(val_dir, transform=val_tf)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=2, pin_memory=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=2, pin_memory=True)
    return train_loader, val_loader, train_ds.classes

@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    correct, total = 0, 0
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        logits = model(x)
        pred = logits.argmax(1)
        correct += (pred == y).sum().item()
        total += y.numel()
    return correct / max(1,total)

def export_onnx(model, out_path, device):
    model.eval()
    dummy = torch.randn(1,3,224,224, device=device)
    out_dir = os.path.dirname(out_path)
    os.makedirs(out_dir, exist_ok=True)
    torch.onnx.export(
        model, dummy, out_path,
        input_names=["input"], output_names=["logits"],
        opset_version=17, dynamic_axes=None
    )
    print("Exported ONNX to", out_path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-dir", required=True)
    ap.add_argument("--val-dir", required=True)
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--out", required=True)  # ONNX output path
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_loader, val_loader, classes = build_dataloaders(args.train_dir, args.val_dir, args.batch_size)

    # MobileNetV3-small transfer learning
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    in_features = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(in_features, len(classes))
    model.to(device)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.AdamW(model.parameters(), lr=args.lr)

    best_acc = 0.0
    best_pt = "artifacts/best.pt"
    os.makedirs("artifacts", exist_ok=True)

    for epoch in range(1, args.epochs+1):
        model.train()
        pbar = tqdm(train_loader, desc=f"Epoch {epoch}/{args.epochs}")
        for x, y in pbar:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = criterion(logits, y)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            pbar.set_postfix(loss=float(loss.item()))

        acc = evaluate(model, val_loader, device)
        print(f"Val acc: {acc:.4f}")
        if acc > best_acc:
            best_acc = acc
            torch.save(model.state_dict(), best_pt)

    # Export ONNX from best weights
    model.load_state_dict(torch.load(best_pt, map_location=device))
    export_onnx(model, args.out, device=device)

    # Save label mapping
    lbl_path = os.path.join(os.path.dirname(args.out), "label_mapping.json")
    label_mapping = {str(i): cls for i, cls in enumerate(classes)}
    with open(lbl_path, "w", encoding="utf-8") as f:
        json.dump(label_mapping, f, indent=2)
    print("Saved label mapping:", lbl_path)
    print("Best val acc:", best_acc)

if __name__ == "__main__":
    main()
