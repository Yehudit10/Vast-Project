# eval_multi_levels.py
import torch
import numpy as np
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, classification_report
from torch.utils.data import DataLoader
import cv2
import albumentations as A
from albumentations.pytorch import ToTensorV2

from agri_baseline.src.detectors.train.dictionary import CLASS_MAPPING
from agri_baseline.src.detectors.cnn_multi_classifier import build_multi_model
from torchvision import datasets
import seaborn as sns
import matplotlib.pyplot as plt

# ------------------------
# Paths
# ------------------------
DATA_DIR = "data_balanced/PlantDoc/test"
MODEL_PATH = "models/cnn_multi_stage3.pth"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# ------------------------
# Transforms
# ------------------------
val_transforms = A.Compose([
    A.Resize(224, 224),
    A.Normalize(mean=(0.485, 0.456, 0.406),
                std=(0.229, 0.224, 0.225)),
    ToTensorV2()
])

# ------------------------
# Dataset wrapper
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
# Prepare dataset
# ------------------------
dataset = datasets.ImageFolder(DATA_DIR)
canonical_classes = sorted(set(CLASS_MAPPING.values()))
class_to_idx = {cls: i for i, cls in enumerate(canonical_classes)}

new_samples, new_targets = [], []
for path, label_idx in dataset.samples:
    raw_name = dataset.classes[label_idx].lower().replace(" ", "_")
    canonical_label = CLASS_MAPPING.get(raw_name)
    if canonical_label is None:
        raise ValueError(f"Class {raw_name} not found in CLASS_MAPPING")
    new_samples.append((path, class_to_idx[canonical_label]))
    new_targets.append(class_to_idx[canonical_label])

dataset.samples = new_samples
dataset.targets = new_targets
dataset.classes = canonical_classes
dataset.class_to_idx = class_to_idx

val_dataset = AlbumentationsDataset(dataset, transform=val_transforms)
val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)

# ------------------------
# Load model
# ------------------------
model = build_multi_model(num_classes=len(canonical_classes)).to(device)
state_dict = torch.load(MODEL_PATH, map_location=device)
model.load_state_dict(state_dict)
model.eval()

# ------------------------
# Evaluation
# ------------------------
all_preds, all_labels = [], []
with torch.no_grad():
    for images, labels in val_loader:
        images, labels = images.to(device), labels.to(device)
        outputs = model(images)
        _, preds = outputs.max(1)
        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(labels.cpu().numpy())

all_preds = np.array(all_preds)
all_labels = np.array(all_labels)

# ------------------------
# Grouping
# ------------------------
def to_healthy_sick(cls: str):
    return "healthy" if "healthy" in cls else "sick"

def to_crop(cls: str):
    if cls.startswith("tomato"): return "tomato"
    if cls.startswith("potato"): return "potato"
    if cls.startswith("pepper"): return "pepper"
    return "other"

def to_disease(cls: str):
    if "bacterial_spot" in cls: return "bacterial_spot"
    if "early_blight" in cls: return "early_blight"
    if "late_blight" in cls: return "late_blight"
    if "leaf_mold" in cls: return "leaf_mold"
    if "septoria_leaf_spot" in cls: return "septoria_leaf_spot"
    if "spider_mites" in cls: return "spider_mites"
    if "target_spot" in cls: return "target_spot"
    if "mosaic_virus" in cls: return "mosaic_virus"
    if "yellowleaf_curl_virus" in cls: return "yellowleaf_curl_virus"
    return "none"

idx_to_class = {v: k for k, v in class_to_idx.items()}

y_true_cls = [idx_to_class[i] for i in all_labels]
y_pred_cls = [idx_to_class[i] for i in all_preds]

# ------------------------
# Evaluation per level
# ------------------------
def evaluate_level(name, y_true, y_pred, labels=None):
    acc = accuracy_score(y_true, y_pred)
    f1 = f1_score(y_true, y_pred, average="weighted")
    print(f"\n===== {name} =====")
    print(f"Accuracy: {acc:.4f}")
    print(f"F1-score (weighted): {f1:.4f}")
    print(classification_report(y_true, y_pred, digits=4))
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    if labels:
        plt.figure(figsize=(8, 6))
        sns.heatmap(cm, annot=True, fmt="d", xticklabels=labels, yticklabels=labels, cmap="Blues")
        plt.title(f"Confusion Matrix - {name}")
        plt.xlabel("Predicted")
        plt.ylabel("True")
        plt.show()

# Healthy vs Sick
evaluate_level("Healthy vs Sick",
               [to_healthy_sick(c) for c in y_true_cls],
               [to_healthy_sick(c) for c in y_pred_cls],
               labels=["healthy", "sick"])

# Crop type
evaluate_level("Crop type",
               [to_crop(c) for c in y_true_cls],
               [to_crop(c) for c in y_pred_cls],
               labels=["tomato", "potato", "pepper", "other"])

# Disease type
evaluate_level("Disease type",
               [to_disease(c) for c in y_true_cls],
               [to_disease(c) for c in y_pred_cls],
               labels=["bacterial_spot","early_blight","late_blight","leaf_mold",
                       "septoria_leaf_spot","spider_mites","target_spot",
                       "mosaic_virus","yellowleaf_curl_virus","none"])
