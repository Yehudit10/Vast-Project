# finetune_multi.py
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import datasets
import os
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader, random_split, WeightedRandomSampler
from torch.optim.lr_scheduler import ReduceLROnPlateau
import albumentations as A
from albumentations.pytorch import ToTensorV2
import cv2
import numpy as np

from agri_baseline.src.detectors.train.dictionary import CLASS_MAPPING
from agri_baseline.src.detectors.cnn_multi_classifier import build_multi_model


# ------------------------
# MixUp
# ------------------------
def mixup_data(x, y, alpha=1.0):
    if alpha > 0:
        lam = np.random.beta(alpha, alpha)
    else:
        lam = 1
    batch_size = x.size()[0]
    index = torch.randperm(batch_size).to(x.device)

    mixed_x = lam * x + (1 - lam) * x[index, :]
    y_a, y_b = y, y[index]
    return mixed_x, y_a, y_b, lam

def mixup_criterion(criterion, pred, y_a, y_b, lam):
    return lam * criterion(pred, y_a) + (1 - lam) * criterion(pred, y_b)


# ------------------------
# Paths
# ------------------------
DATA_DIR = "data_balanced/PlantDoc"
MODEL_PATH = "models/cnn_multi.pth"
SAVE_PATH = "models/cnn_multi_finetuned.pth"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ------------------------
# Augmentations
# ------------------------
train_transforms = A.Compose([
    A.RandomResizedCrop(size=(224, 224), scale=(0.7, 1.0), p=1.0),
    A.HorizontalFlip(p=0.5),
    A.VerticalFlip(p=0.3),
    A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.2, rotate_limit=30, p=0.7),
    A.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, p=0.5),
    A.RandomBrightnessContrast(p=0.5),
    A.GaussianBlur(p=0.3),
    A.CoarseDropout(max_height=32, max_width=32, max_holes=1, p=0.3),
    A.Normalize(mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225)),
    ToTensorV2()
])

val_transforms = A.Compose([
    A.Resize(224, 224),
    A.Normalize(mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225)),
    ToTensorV2()
])


# ------------------------
# Albumentations Dataset
# ------------------------
class AlbumentationsDataset(torch.utils.data.Dataset):
    def __init__(self, dataset, transform=None):
        self.dataset = dataset
        self.transform = transform

    def __getitem__(self, idx):
        path, label = self.dataset.samples[idx]
        image = cv2.imread(path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        if self.transform:
            image = self.transform(image=image)["image"]
        return image, label

    def __len__(self):
        return len(self.dataset)


# ------------------------
# Prepare Dataset
# ------------------------
def prepare_multi_dataset(path):
    dataset = datasets.ImageFolder(path)
    new_samples, new_targets = [], []
    canonical_classes = sorted(set(CLASS_MAPPING.values()))
    class_to_idx = {cls: i for i, cls in enumerate(canonical_classes)}

    for sample_path, label_idx in dataset.samples:
        raw_name = dataset.classes[label_idx].lower().replace(" ", "_")
        canonical_label = CLASS_MAPPING.get(raw_name)
        if canonical_label is None:
            raise ValueError(f"Class {raw_name} not found in CLASS_MAPPING")
        new_samples.append((sample_path, class_to_idx[canonical_label]))
        new_targets.append(class_to_idx[canonical_label])

    dataset.samples = new_samples
    dataset.targets = new_targets
    dataset.classes = canonical_classes
    dataset.class_to_idx = class_to_idx
    return dataset


# ------------------------
# Load dataset
# ------------------------
full_dataset = prepare_multi_dataset(os.path.join(DATA_DIR, "train"))
print("Classes:", full_dataset.classes)
print("Total samples:", len(full_dataset))

train_size = int(0.8 * len(full_dataset))
val_size = len(full_dataset) - train_size
train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size])

train_dataset = AlbumentationsDataset(train_dataset.dataset, transform=train_transforms)
val_dataset = AlbumentationsDataset(val_dataset.dataset, transform=val_transforms)

class_counts = np.bincount(full_dataset.targets)
class_weights = 1. / class_counts
sample_weights = [class_weights[t] for t in full_dataset.targets]

sampler = WeightedRandomSampler(weights=sample_weights,
                                num_samples=len(sample_weights),
                                replacement=True)

train_loader = DataLoader(train_dataset, batch_size=32, sampler=sampler)
val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)


# ------------------------
# Model
# ------------------------
model = build_multi_model(num_classes=len(full_dataset.classes)).to(device)
state_dict = torch.load(MODEL_PATH, map_location=device)
filtered_state_dict = {k: v for k, v in state_dict.items() if not k.startswith("fc.")}
model.load_state_dict(filtered_state_dict, strict=False)
print("✅ Loaded pretrained backbone")


# ------------------------
# Training setup
# ------------------------
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam([
    {"params": model.fc.parameters(), "lr": 1e-3},
], lr=1e-3)

scheduler = ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3, verbose=True)
best_val_f1 = 0.0
patience, counter = 5, 0


# ------------------------
# Gradual Unfreeze
# ------------------------
def unfreeze(epoch):
    if epoch == 5:
        for name, param in model.named_parameters():
            if "layer4" in name:
                param.requires_grad = True
    if epoch == 10:
        for param in model.parameters():
            param.requires_grad = True


# ------------------------
# Training Loop
# ------------------------
EPOCHS = 20
for epoch in range(EPOCHS):
    unfreeze(epoch)
    model.train()
    total_loss, correct, total = 0.0, 0, 0
    for images, labels in train_loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        images, targets_a, targets_b, lam = mixup_data(images, labels, alpha=0.4)
        outputs = model(images)
        loss = mixup_criterion(criterion, outputs, targets_a, targets_b, lam)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * images.size(0)
        _, preds = outputs.max(1)
        correct += preds.eq(labels).sum().item()
        total += labels.size(0)

    train_acc = correct / total
    train_loss = total_loss / total

    # Validation
    model.eval()
    all_preds, all_labels = [], []
    val_loss, val_correct, val_total = 0.0, 0, 0
    with torch.no_grad():
        for images, labels in val_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels)
            val_loss += loss.item() * images.size(0)
            _, preds = outputs.max(1)
            val_correct += preds.eq(labels).sum().item()
            val_total += labels.size(0)
            all_preds.extend(preds.cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

    val_acc = val_correct / val_total
    val_loss /= val_total
    val_f1 = f1_score(all_labels, all_preds, average="weighted")

    print(f"Epoch {epoch+1}/{EPOCHS} "
          f"Train Loss: {train_loss:.4f}, Train Acc: {train_acc:.4f} "
          f"Val Loss: {val_loss:.4f}, Val Acc: {val_acc:.4f}, Val F1: {val_f1:.4f}")

    scheduler.step(val_loss)

    # Save by F1
    if val_f1 > best_val_f1:
        best_val_f1 = val_f1
        counter = 0
        torch.save(model.state_dict(), SAVE_PATH)
        print("💾 Model improved (F1) and saved!")
    else:
        counter += 1
        print(f"⏳ No improvement. EarlyStopping counter: {counter}/{patience}")
        if counter >= patience:
            print("🛑 Early stopping triggered!")
            break

print(f"✅ Training finished. Best model saved to {SAVE_PATH}")
