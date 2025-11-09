# models/evaluate.py
# ---------------------------------------------------------------------
# Lightweight & robust evaluation for a binary UNet segmentation model.
# - Safe on Windows (no anonymous lambdas; workers=0 by default)
# - Normalizes mask to {0,1} so BCEWithLogitsLoss behaves correctly
# - Matches logits size to mask to avoid shape errors
# - Clamps logits to [-20, 20] to prevent numerical blow-ups in BCE
# - Tiny default IMG_SIZE (16x16) for very fast CPU sanity checks
# - Prints ETA, IoU/Dice, Dice-Loss, one-batch profile, and optional
#   best-threshold sweep on the cached validation subset
# ---------------------------------------------------------------------

import os
import time
import random
import argparse
from typing import Tuple, List, Dict, Any

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader, Subset
from torchvision import transforms
from torchvision.transforms import InterpolationMode

from models.unet_model import UNet
from models.dataset import WeedsFromTables as DeepWeedsDataset

# Keep machine responsive (mirror your train.py)
torch.set_num_threads(1)

# ----------------------- Defaults ------------------------------------

ROOT = "data"
LABELS_DIR = os.path.join(ROOT, "labels")
MASKS_DIR = "masks"
IMAGE_COL = "Filename"
IMG_SIZE_DEFAULT: Tuple[int, int] = (16, 16)  # tiny & fast (matches your train.py)
WEIGHTS_DEFAULT = "models/unet_weedseg_best.pth"
VAL_PREFIX_DEFAULT = "val_subset"

FAST_DEBUG_DEFAULT = True
SUBSET_SIZE_VAL_DEFAULT = 200
MAX_STEPS_EVAL_DEFAULT = 100
PRINT_EVERY_DEFAULT = 10

BATCH_SIZE_DEFAULT = 1   # safe/light on CPU
WORKERS_DEFAULT = 0      # Windows-safe (no pickling issues)

CLAMP_LOGITS: Tuple[float, float] = (-20.0, 20.0)  # stabilize BCE

# ----------------------- Picklable transforms -------------------------

class MaskTo01(object):
    """
    Convert [1,H,W] uint8 {0,255} mask from PILToTensor to [H,W] long {0,1}.
    Kept as a top-level class so it's picklable on Windows.
    """
    def __call__(self, t: torch.Tensor) -> torch.Tensor:
        t = t.squeeze(0)                 # [H,W] uint8
        return (t > 0).to(torch.long)    # [H,W] long {0,1}

def build_transforms(img_size: Tuple[int, int]):
    image_tf = transforms.Compose([
        transforms.Resize(img_size, interpolation=InterpolationMode.BILINEAR),
        transforms.ToTensor(),  # [C,H,W] float in [0,1]
    ])
    mask_tf = transforms.Compose([
        transforms.Resize(img_size, interpolation=InterpolationMode.NEAREST),
        transforms.PILToTensor(),  # [1,H,W] uint8 (0 or 255)
        MaskTo01(),                # [H,W] long {0,1}
    ])
    return image_tf, mask_tf

# ----------------------- Dataset utils --------------------------------

def collect_tables(labels_dir: str, prefix: str) -> List[str]:
    files = []
    for f in os.listdir(labels_dir):
        name = f.lower()
        if name.startswith(prefix.lower()) and (name.endswith(".csv") or name.endswith(".xlsx")):
            files.append(os.path.join(labels_dir, f))
    if not files:
        raise RuntimeError(f"No files with prefix '{prefix}' found in {labels_dir}")
    return sorted(files)

def make_subset(ds, k: int, use_subset: bool, seed: int = 1337):
    if not use_subset:
        return ds
    k = min(k, len(ds))
    rng = random.Random(seed)
    idx = rng.sample(range(len(ds)), k)
    print(f"FAST_DEBUG: evaluating on subset of {k}/{len(ds)} examples")
    return Subset(ds, idx)

# ----------------------- Core helpers ---------------------------------

def _match_logits_to_mask(logits: torch.Tensor, mask_hw: Tuple[int, int]) -> torch.Tensor:
    """Ensure the logits spatial size matches the target mask."""
    if tuple(logits.shape[-2:]) != tuple(mask_hw):
        logits = F.interpolate(logits, size=mask_hw, mode="bilinear", align_corners=False)
    return logits

def iou_dice(pred01: torch.Tensor, tgt01: torch.Tensor):
    """pred01,tgt01: [H,W] {0,1} uint8/long."""
    inter = (pred01 & tgt01).sum().item()
    union = (pred01 | tgt01).sum().item()
    iou = inter / (union + 1e-8)
    dice = (2 * inter) / (pred01.sum().item() + tgt01.sum().item() + 1e-8)
    return float(iou), float(dice)

def dice_loss_from_probs(prob: torch.Tensor, target: torch.Tensor, eps: float = 1e-6) -> float:
    """
    prob,target: [B,1,H,W] float in [0,1]
    Returns mean Dice loss over the batch.
    """
    inter = (prob * target).sum(dim=(1, 2, 3))
    denom = prob.sum(dim=(1, 2, 3)) + target.sum(dim=(1, 2, 3))
    dl = 1.0 - (2.0 * inter + eps) / (denom + eps)
    return float(dl.mean().item())

def find_best_threshold(probs_list: List, masks_list: List) -> Tuple[float, float]:
    """Grid-search a good probability threshold on cached samples."""
    import numpy as np
    ths = np.linspace(0.1, 0.9, 17)
    best_t, best_dice = 0.5, -1.0
    for t in ths:
        dices = []
        for p, m in zip(probs_list, masks_list):
            pred01 = (p > t).astype("uint8")
            inter = (pred01 & m).sum()
            dices.append((2 * inter) / (pred01.sum() + m.sum() + 1e-8))
        md = float(np.mean(dices)) if dices else -1.0
        if md > best_dice:
            best_dice, best_t = md, float(t)
    return best_t, best_dice

# ----------------------- Profiling ------------------------------------

@torch.no_grad()
def profile_one_batch(model, loader, device) -> Dict[str, Any]:
    """Quick timing of one batch to sense where the time goes."""
    t0 = time.time()
    images, masks = next(iter(loader))
    t1 = time.time()
    images = images.to(device)
    masks  = masks.unsqueeze(1).float().to(device)
    t2 = time.time()
    logits = model(images)
    logits = _match_logits_to_mask(logits, masks.shape[-2:])
    t3 = time.time()
    return {
        "load_s": t1 - t0,
        "to_device_s": t2 - t1,
        "forward_s": t3 - t2,
        "total_s": t3 - t0,
        "img_shape": tuple(images.shape),
        "logits_shape": tuple(logits.shape),
        "mask_unique": torch.unique(masks[0,0].cpu())
    }

# ----------------------- Evaluation -----------------------------------

@torch.inference_mode()
def evaluate(model: torch.nn.Module,
             loader: DataLoader,
             device: torch.device,
             print_every: int = 10,
             max_steps: int | None = None,
             do_threshold_sweep: bool = True) -> None:
    criterion = torch.nn.BCEWithLogitsLoss()

    total_bce = 0.0
    total_dice_loss = 0.0
    iou_sum, dice_sum = 0.0, 0.0
    n_valid = 0

    t0 = time.time()
    total_steps = len(loader) if max_steps is None else min(len(loader), max_steps)

    # cache a small set for threshold sweep
    probs_cache, masks_cache = [], []

    for step, (imgs, masks) in enumerate(loader, 1):
        imgs = imgs.to(device)                          # [B,3,H,W]
        masks = masks.unsqueeze(1).float().to(device)   # [B,1,H,W] float {0,1}

        logits = model(imgs)                            # [B,1,h,w]
        logits = _match_logits_to_mask(logits, masks.shape[-2:])

        if step == 1:
            print("shapes:", tuple(imgs.shape), tuple(logits.shape), tuple(masks.shape))
            print("mask unique (should be {0.,1.}):", torch.unique(masks[0,0].cpu()))
            # Logits diagnostics
            print("logits stats -> min/max/mean/std:",
                  logits.min().item(), logits.max().item(),
                  logits.mean().item(), logits.std().item())

        # Stabilize BCE against extreme logits
        logits = torch.clamp(logits, CLAMP_LOGITS[0], CLAMP_LOGITS[1])

        bce = criterion(logits, masks)
        if not torch.isfinite(bce):
            print(f"  step {step}: non-finite loss -> skipped")
            continue

        total_bce += float(bce.item())
        n_valid += 1

        prob = torch.sigmoid(logits)
        total_dice_loss += dice_loss_from_probs(prob, masks)

        # threshold 0.5 metrics
        pred01 = (prob > 0.5).to(torch.uint8)[0, 0].cpu()
        tgt01  = masks[0, 0].to(torch.uint8).cpu()
        iou, dice = iou_dice(pred01, tgt01)
        iou_sum += iou; dice_sum += dice

        # cache for sweep
        if do_threshold_sweep and len(probs_cache) < (total_steps if max_steps else 200):
            probs_cache.append(prob[0,0].cpu().numpy())
            masks_cache.append(tgt01.cpu().numpy())

        if step == 1 or step % print_every == 0:
            elapsed = time.time() - t0
            eta = elapsed / step * (total_steps - step)
            print(f"  step {step}/{total_steps} | BCE={total_bce/max(1,n_valid):.4f} "
                  f"| DiceLoss={total_dice_loss/max(1,n_valid):.4f} "
                  f"| IoU@0.5={iou_sum/max(1,n_valid):.4f} | Dice@0.5={dice_sum/max(1,n_valid):.4f} "
                  f"| ETA={int(eta//60)}m {int(eta%60)}s")

        if (max_steps is not None) and (step >= max_steps):
            break

    if n_valid == 0:
        print("No valid samples evaluated.")
        return

    print("\n===== VALIDATION SUMMARY =====")
    print(f"BCE={total_bce/n_valid:.4f} | DiceLoss={total_dice_loss/n_valid:.4f} "
          f"| IoU@0.5={iou_sum/n_valid:.4f} | Dice@0.5={dice_sum/n_valid:.4f} | N={n_valid}")

    # Optional: threshold sweep report
    if do_threshold_sweep and probs_cache:
        try:
            best_t, best_dice = find_best_threshold(probs_cache, masks_cache)
            print(f"Best threshold on VAL (grid 0.1..0.9): t={best_t:.2f} | Dice={best_dice:.4f}")
        except Exception as e:
            print(f"(threshold sweep skipped: {e})")

# ----------------------- CLI/Main -------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Lightweight evaluation for UNet weed segmentation.")
    p.add_argument("--root", type=str, default=ROOT)
    p.add_argument("--labels_dir", type=str, default=LABELS_DIR)
    p.add_argument("--val_prefix", type=str, default=VAL_PREFIX_DEFAULT)
    p.add_argument("--masks_dir", type=str, default=MASKS_DIR)
    p.add_argument("--image_col", type=str, default=IMAGE_COL)
    p.add_argument("--img_size", type=int, nargs=2, default=list(IMG_SIZE_DEFAULT))  # H W
    p.add_argument("--weights", type=str, default=WEIGHTS_DEFAULT)

    p.add_argument("--fast_debug", action="store_true", default=FAST_DEBUG_DEFAULT)
    p.add_argument("--subset", type=int, default=SUBSET_SIZE_VAL_DEFAULT)
    p.add_argument("--max_steps", type=int, default=MAX_STEPS_EVAL_DEFAULT)

    p.add_argument("--batch_size", type=int, default=BATCH_SIZE_DEFAULT)
    p.add_argument("--workers", type=int, default=WORKERS_DEFAULT)  # keep 0 on Windows
    p.add_argument("--print_every", type=int, default=PRINT_EVERY_DEFAULT)
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--no_thresh_sweep", action="store_true", help="Disable best-threshold sweep")
    return p.parse_args()

def main():
    args = parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print("Device:", device)

    image_tf, mask_tf = build_transforms(tuple(args.img_size))
    val_tables = collect_tables(args.labels_dir, args.val_prefix)

    val_full = DeepWeedsDataset(
        root_dir=args.root,
        table_files=val_tables,
        labels_file=None,
        image_col=args.image_col,
        box_cols=None,        # using mask files
        class_col=None,       # binary from mask
        image_transform=image_tf,
        mask_transform=mask_tf,
        masks_dir=args.masks_dir,
    )

    val_dataset = make_subset(val_full, args.subset, args.fast_debug, seed=args.seed)

    val_loader = DataLoader(
        val_dataset,
        batch_size=max(1, args.batch_size),
        shuffle=False,
        num_workers=max(0, args.workers),  # 0 by default → Windows-safe
        pin_memory=False,                  # CPU path
        persistent_workers=False,
    )

    model = UNet(in_channels=3, out_channels=1).to(device)
    state = torch.load(args.weights, map_location=device)
    model.load_state_dict(state, strict=True)
    model.eval()

    # one-batch profile (helps detect bottlenecks quickly)
    prof = profile_one_batch(model, val_loader, device)
    print(f"PROFILE one batch -> load={prof['load_s']:.3f}s | to_device={prof['to_device_s']:.3f}s | "
          f"forward={prof['forward_s']:.3f}s | total={prof['total_s']:.3f}s | "
          f"img={prof['img_shape']} | logits={prof['logits_shape']} | mask_unique={prof['mask_unique']}")

    evaluate(
        model, val_loader, device,
        print_every=args.print_every,
        max_steps=(args.max_steps if args.fast_debug else None),
        do_threshold_sweep=(not args.no_thresh_sweep)
    )

if __name__ == "__main__":
    main()
