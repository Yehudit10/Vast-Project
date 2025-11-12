# models/train.py
# ---------------------------------------------------------------------
# Lightweight UNet training loop (CPU/Windows friendly).
# Key fixes:
#  - Masks are normalized to {0,1} (not {0,255}) via a picklable transform.
#  - Size-mismatch safety: logits are resized to target HxW before loss.
#  - Optional BCE+Dice combined loss (helps class imbalance).
#  - Gradient clipping to prevent exploding updates.
# Defaults mirror your "light" config: tiny IMG_SIZE, batch_size=1, workers=0.
# ---------------------------------------------------------------------

import os
import time
import random
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
from torchvision.transforms import InterpolationMode

from models.unet_model import UNet
from models.dataset import WeedsFromTables as DeepWeedsDataset

print(torch.cuda.is_available())

# Keep machine responsive on CPU
torch.set_num_threads(1)

# ===================== Run Config =====================
ROOT = "data"
LABELS_DIR = os.path.join(ROOT, "labels")

# Fast debug to verify pipeline end-to-end
FAST_DEBUG         = False    # set to False for full training
SUBSET_SIZE_TRAIN  = 500
SUBSET_SIZE_VAL    = 200
MAX_STEPS_TRAIN    = 20
MAX_STEPS_VAL      = 100
PRINT_EVERY        = 10

# Table column names
IMAGE_COL = "Filename"
BOX_COLS  = None
CLASS_COL = None

# Small input for fast CPU sanity checks (can raise to 128x128 later)
IMG_SIZE = (64, 64)

# Training knobs
LR = 1e-3
WEIGHT_DECAY = 1e-4
GRAD_CLIP_NORM = 5.0          # set None to disable
USE_DICE_MIX = True           # True -> (BCE + DiceLoss)/2
SAVE_DIR = "models"
BEST_WEIGHTS_PATH = os.path.join(SAVE_DIR, "unet_weedseg_best.pth")
LAST_WEIGHTS_PATH = os.path.join(SAVE_DIR, "unet_weedseg_last.pth")
SEED = 1337
# ======================================================

# ------------------- Reproducibility -------------------
def set_seed(seed: int = 1337):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
set_seed(SEED)

# ------------------- Table collection ------------------
def collect(prefix: str):
    files = []
    for f in os.listdir(LABELS_DIR):
        name = f.lower()
        if name.startswith(prefix.lower()) and (name.endswith(".xlsx") or name.endswith(".csv")):
            files.append(os.path.join(LABELS_DIR, f))
    if not files:
        raise RuntimeError(f"No {prefix} files found in {LABELS_DIR}")
    return sorted(files)

# ------------------- Subset helper ---------------------
def make_subset(ds, k: int):
    n = len(ds)
    if k is None or n <= k:
        return ds
    idxs = random.sample(range(n), k)
    return Subset(ds, idxs)

# ------------------- Transforms ------------------------
class MaskTo01(object):
    """
    Convert [1,H,W] uint8 {0,255} from PILToTensor to [H,W] long {0,1}.
    Kept as a top-level class so it's picklable on Windows.
    """
    def __call__(self, t: torch.Tensor) -> torch.Tensor:
        t = t.squeeze(0)               # [H,W] uint8
        return (t > 0).to(torch.long)  # [H,W] 0/1

image_tf = transforms.Compose([
    transforms.Resize(IMG_SIZE, interpolation=InterpolationMode.BILINEAR),
    transforms.ToTensor(),  # -> [C,H,W], float in [0,1]
])

mask_tf = transforms.Compose([
    transforms.Resize(IMG_SIZE, interpolation=InterpolationMode.NEAREST),
    transforms.PILToTensor(),  # -> [1,H,W] uint8 (0 or 255)
    MaskTo01(),                # -> [H,W] long {0,1}
])

# ------------------- Datasets --------------------------
train_tables = collect("train_subset")
val_tables   = collect("val_subset")
labels_file  = None

train_dataset_full = DeepWeedsDataset(
    root_dir=ROOT,
    table_files=train_tables,
    labels_file=labels_file,
    image_col=IMAGE_COL,
    box_cols=BOX_COLS,
    class_col=CLASS_COL,
    image_transform=image_tf,
    mask_transform=mask_tf,
    masks_dir="masks",
)
val_dataset_full = DeepWeedsDataset(
    root_dir=ROOT,
    table_files=val_tables,
    labels_file=labels_file,
    image_col=IMAGE_COL,
    box_cols=BOX_COLS,
    class_col=CLASS_COL,
    image_transform=image_tf,
    mask_transform=mask_tf,
    masks_dir="masks",
)

if FAST_DEBUG:
    print("FAST_DEBUG: using small subsets")
    train_dataset = make_subset(train_dataset_full, SUBSET_SIZE_TRAIN)
    val_dataset   = make_subset(val_dataset_full,   SUBSET_SIZE_VAL)
else:
    train_dataset = train_dataset_full
    val_dataset   = val_dataset_full

# ------------------- DataLoaders -----------------------
# Windows-safe: workers=0; batch_size=1 for low CPU pressure
train_loader = DataLoader(
    train_dataset, batch_size=1, shuffle=True,
    num_workers=0, pin_memory=False
)
val_loader = DataLoader(
    val_dataset, batch_size=1, shuffle=False,
    num_workers=0, pin_memory=False
)

# ------------------- Model & Optimizer -----------------
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = UNet(in_channels=3, out_channels=1).to(device)

bce = nn.BCEWithLogitsLoss()
optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

# ------------------- Helpers ---------------------------
def _match_logits_to_mask(logits: torch.Tensor, mask_hw):
    """Resize logits to [*,1,H,W] to match target before loss."""
    if logits.shape[-2:] != mask_hw:
        logits = F.interpolate(logits, size=mask_hw, mode="bilinear", align_corners=False)
    return logits

def dice_loss_from_logits(logits: torch.Tensor, target01: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    """
    logits: [B,1,H,W] (raw)
    target01: [B,1,H,W] float {0,1}
    returns scalar tensor
    """
    prob = torch.sigmoid(logits)
    inter = (prob * target01).sum(dim=(1,2,3))
    denom = prob.sum(dim=(1,2,3)) + target01.sum(dim=(1,2,3))
    dl = 1.0 - (2.0 * inter + eps) / (denom + eps)
    return dl.mean()

@torch.no_grad()
def pixel_accuracy_from_logits(logits, target01, threshold=0.5):
    """
    logits: [B,1,H,W] - פלט המודל לפני sigmoid
    target01: [B,1,H,W] - מסכה עם 0/1
    threshold: סף בינארי (לרוב 0.5)
    """
    probs = torch.sigmoid(logits)
    preds = (probs > threshold).float()
    correct = (preds == target01).float().sum()
    total = target01.numel()
    return (correct / total).item()

def combined_loss(logits: torch.Tensor, target01: torch.Tensor) -> torch.Tensor:
    if USE_DICE_MIX:
        return 0.5 * bce(logits, target01) + 0.5 * dice_loss_from_logits(logits, target01)
    else:
        return bce(logits, target01)

# ------------------- One-batch profile -----------------
@torch.no_grad()
def profile_one_batch(model, loader, device):
    model.eval()
    t0 = time.time()
    images, masks = next(iter(loader))
    t1 = time.time()
    images = images.to(device)
    masks  = masks.unsqueeze(1).float().to(device)
    t2 = time.time()
    logits = model(images)
    logits = _match_logits_to_mask(logits, masks.shape[-2:])
    t3 = time.time()
    # quick sanity check
    print("PROFILE shapes:", tuple(images.shape), tuple(masks.shape), tuple(logits.shape))
    print("mask unique (should be {0.,1.}):", torch.unique(masks[0,0].detach().cpu()))
    return {
        "load_s": t1 - t0,
        "to_device_s": t2 - t1,
        "forward_s": t3 - t2,
        "total_s": t3 - t0,
        "img_shape": tuple(images.shape),
    }

# ------------------- Train / Val loops -----------------
_printed_debug_shapes = False

def train_one_epoch(model, loader, optimizer, device, max_steps=None):
    global _printed_debug_shapes
    model.train()
    running = 0.0
    t_start = time.time()

    for step, (images, masks) in enumerate(loader, 1):
        if not _printed_debug_shapes:
            print("DEBUG shapes:", tuple(images.shape), tuple(masks.shape))  # (B,3,H,W), (B,H,W)
            _printed_debug_shapes = True

        images = images.to(device)                       # [B,3,H,W]
        masks  = masks.unsqueeze(1).float().to(device)   # [B,1,H,W] float {0,1}

        optimizer.zero_grad(set_to_none=True)
        logits = model(images)                           # [B,1,h,w]
        logits = _match_logits_to_mask(logits, masks.shape[-2:])

        loss = combined_loss(logits, masks)
        loss.backward()

        if GRAD_CLIP_NORM is not None:
            torch.nn.utils.clip_grad_norm_(model.parameters(), GRAD_CLIP_NORM)

        optimizer.step()

        running += loss.item()

        if step % PRINT_EVERY == 0 or step == 1:
            print(f"  step {step}/{len(loader)} | loss={running/step:.4f}")

        if (max_steps is not None) and (step >= max_steps):
            break

    denom = min(len(loader), max_steps) if max_steps else len(loader)
    epoch_time = time.time() - t_start
    print(f"  epoch avg step: {epoch_time/denom:.3f}s | epoch total: {epoch_time:.1f}s")
    return running / max(1, denom)
@torch.no_grad()
def validate(model, loader, device, max_steps=None):
    model.eval()
    running_loss = 0.0
    running_acc  = 0.0
    count = 0
    t_start = time.time()

    for step, (images, masks) in enumerate(loader, 1):
        images = images.to(device)
        masks  = masks.unsqueeze(1).float().to(device)
        logits = model(images)
        logits = _match_logits_to_mask(logits, masks.shape[-2:])
        loss = combined_loss(logits, masks)
        acc  = pixel_accuracy_from_logits(logits, masks)

        running_loss += loss.item()
        running_acc  += acc
        count += 1

        if step % PRINT_EVERY == 0 or step == 1:
            print(f"  [val] step {step}/{len(loader)} | loss={running_loss/count:.4f} | acc={running_acc/count:.4f}")

        if (max_steps is not None) and (step >= max_steps):
            break

    denom = max(1, count)
    epoch_time = time.time() - t_start
    print(f"  [val] epoch avg step: {epoch_time/denom:.3f}s | epoch total: {epoch_time:.1f}s")
    avg_loss = running_loss / denom
    avg_acc  = running_acc  / denom
    return avg_loss, avg_acc

# ------------------- Main ------------------------------
def main():
    epochs = 3 if FAST_DEBUG else 20
    best_val = float("inf")
    os.makedirs(SAVE_DIR, exist_ok=True)

    # One-batch profile to understand timing
    prof = profile_one_batch(model, train_loader, device)
    print(f"PROFILE one batch -> load={prof['load_s']:.3f}s | to_device={prof['to_device_s']:.3f}s | "
          f"forward={prof['forward_s']:.3f}s | total={prof['total_s']:.3f}s | shape={prof['img_shape']}")

    for epoch in range(1, epochs + 1):
        print(f"\nEpoch {epoch}/{epochs}")

        train_loss = train_one_epoch(
            model, train_loader, optimizer, device,
            max_steps=(MAX_STEPS_TRAIN if FAST_DEBUG else None)
        )

        val_loss, val_acc = validate(
            model, val_loader, device,
            max_steps=(MAX_STEPS_VAL if FAST_DEBUG else None)
        )

        print(f"Epoch {epoch:02d} | train_loss={train_loss:.4f} | val_loss={val_loss:.4f} | val_acc={val_acc:.4f}")

        if val_loss < best_val:
            best_val = val_loss
            torch.save(model.state_dict(), BEST_WEIGHTS_PATH)
            print(f"✓ Saved best -> {BEST_WEIGHTS_PATH} (val={best_val:.4f})")

    torch.save(model.state_dict(), LAST_WEIGHTS_PATH)
    print(f"✓ Saved last -> {LAST_WEIGHTS_PATH}")

if __name__ == "__main__":
    main()
