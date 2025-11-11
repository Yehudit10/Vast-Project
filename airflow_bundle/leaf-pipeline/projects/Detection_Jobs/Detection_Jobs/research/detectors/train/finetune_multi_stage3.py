# finetune_multi_stage3.py
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, random_split
import albumentations as A
from albumentations.pytorch import ToTensorV2
import cv2, os
import numpy as np
from sklearn.metrics import f1_score

from agri_baseline.src.detectors.train.dictionary import CLASS_MAPPING
from agri_baseline.src.detectors.cnn_multi_classifier import build_multi_model
from torchvision import datasets

# =========================
# Config
# =========================
DATA_DIR = "data_balanced/PlantDoc"
PREV_MODEL = "models/cnn_multi_finetuned.pth" 
SAVE_PATH  = "models/cnn_multi_stage3.pth"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# =========================
# Augmentations
# =========================
train_tfms = A.Compose([
    A.RandomResizedCrop(size=(224, 224), scale=(0.6, 1.0), p=1.0),
    A.HorizontalFlip(p=0.5),
    A.VerticalFlip(p=0.3),
    A.RandomBrightnessContrast(p=0.4),
    A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.2, rotate_limit=30, p=0.5),
    A.GaussianBlur(p=0.2),
    A.RandomGamma(p=0.3),
    A.Normalize(mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225)),
    ToTensorV2()
])

val_tfms = A.Compose([
    A.Resize(224, 224),
    A.Normalize(mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225)),
    ToTensorV2()
])


# =========================
# Dataset wrapper
# =========================
class AlbumentationsDataset(torch.utils.data.Dataset):
    def __init__(self, dataset, transform=None):
        self.dataset = dataset
        self.transform = transform

    def __getitem__(self, idx):
        path, label = self.dataset.samples[idx]
        img = cv2.imread(path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if self.transform:
            img = self.transform(image=img)["image"]
        return img, label

    def __len__(self):
        return len(self.dataset)


def prepare_dataset(path):
    ds = datasets.ImageFolder(path)
    new_samples, new_targets = [], []
    canonical = sorted(set(CLASS_MAPPING.values()))
    class_to_idx = {cls: i for i, cls in enumerate(canonical)}

    for pth, idx in ds.samples:
        raw = ds.classes[idx].lower().replace(" ", "_")
        canon = CLASS_MAPPING.get(raw)
        if canon is None:
            raise ValueError(f"Class {raw} missing in CLASS_MAPPING")
        new_samples.append((pth, class_to_idx[canon]))
        new_targets.append(class_to_idx[canon])

    ds.samples = new_samples
    ds.targets = new_targets
    ds.classes = canonical
    ds.class_to_idx = class_to_idx
    return ds


# =========================
# Progressive unfreezing
# =========================
def unfreeze_layers(model, stages):
    """
    stages: List of layer names to release (e.g.: ["layer3", "layer2"])
    """
    for name, param in model.named_parameters():
        for stage in stages:
            if stage in name:
                param.requires_grad = True


# =========================
# Training loop
# =========================
def train_stage3(model, train_loader, val_loader, epochs=20):
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=1e-4)

    best_f1, patience, counter = 0, 5, 0
    for epoch in range(epochs):
        model.train()
        total_loss, total_correct, total = 0, 0, 0
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            out = model(xb)
            loss = criterion(out, yb)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * xb.size(0)
            _, preds = out.max(1)
            total_correct += preds.eq(yb).sum().item()
            total += yb.size(0)

        train_acc = total_correct / total
        train_loss = total_loss / total

        # Validation
        model.eval()
        val_loss, val_correct, val_total = 0, 0, 0
        all_preds, all_labels = [], []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(device), yb.to(device)
                out = model(xb)
                loss = criterion(out, yb)
                val_loss += loss.item() * xb.size(0)
                _, preds = out.max(1)
                val_correct += preds.eq(yb).sum().item()
                val_total += yb.size(0)
                all_preds.extend(preds.cpu().numpy())
                all_labels.extend(yb.cpu().numpy())

        val_acc = val_correct / val_total
        val_loss /= val_total
        val_f1 = f1_score(all_labels, all_preds, average="weighted")

        print(f"Epoch {epoch+1}/{epochs} | Train Loss: {train_loss:.4f} Acc: {train_acc:.3f} "
              f"| Val Loss: {val_loss:.4f} Acc: {val_acc:.3f} F1: {val_f1:.3f}")

        if val_f1 > best_f1:
            best_f1 = val_f1
            counter = 0
            torch.save(model.state_dict(), SAVE_PATH)
            print(f"💾 Model improved (F1={val_f1:.3f}) and saved!")
        else:
            counter += 1
            if counter >= patience:
                print("🛑 EarlyStopping triggered.")
                break


# =========================
# Main
# =========================
if __name__ == "__main__":
    full_ds = prepare_dataset(os.path.join(DATA_DIR, "train"))
    train_size = int(0.8 * len(full_ds))
    val_size = len(full_ds) - train_size
    train_ds, val_ds = random_split(full_ds, [train_size, val_size])

    train_ds = AlbumentationsDataset(train_ds.dataset, transform=train_tfms)
    val_ds   = AlbumentationsDataset(val_ds.dataset, transform=val_tfms)

    train_loader = DataLoader(train_ds, batch_size=32, shuffle=True)
    val_loader   = DataLoader(val_ds, batch_size=32)

    model = build_multi_model(num_classes=len(full_ds.classes)).to(device)
    model.load_state_dict(torch.load(PREV_MODEL, map_location=device))

    # In step 3 we will release additional layers beyond layer4
    for p in model.parameters():
        p.requires_grad = False
    for stage in ["layer3", "layer4", "fc"]:
        unfreeze_layers(model, [stage])
        print(f"🔓 Unfroze {stage}")

    train_stage3(model, train_loader, val_loader, epochs=15)
    print(f"✅ Training done. Best model saved to {SAVE_PATH}")
