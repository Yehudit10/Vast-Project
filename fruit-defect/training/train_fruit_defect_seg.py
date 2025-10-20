# """
# Train U-Net for strawberry disease segmentation (defect masks).
# Expects images in train/val folders, and PNG masks in train_masks/val_masks.
# """

# import os
# import yaml
# import random
# import numpy as np
# from pathlib import Path
# from PIL import Image
# from tqdm import tqdm

# import torch
# import torch.nn as nn
# from torch.utils.data import Dataset, DataLoader
# from torchvision import transforms

# # reproducibility
# def set_seed(seed=42):
#     random.seed(seed)
#     np.random.seed(seed)
#     torch.manual_seed(seed)
#     torch.cuda.manual_seed_all(seed)
#     torch.backends.cudnn.deterministic = True
#     torch.backends.cudnn.benchmark = False

# # =========================
# # Dataset
# # =========================
# class SegDataset(Dataset):
#     def __init__(self, img_dir, mask_dir, size=256, augment=False):
#         self.img_dir = Path(img_dir)
#         self.mask_dir = Path(mask_dir)
#         self.images = sorted([p for p in self.img_dir.glob("*.jpg")])
#         self.size = size
#         self.augment = augment

#         self.tf_img = transforms.Compose([
#             transforms.Resize((size, size)),
#             transforms.ToTensor(),
#             transforms.Normalize([0.485,0.456,0.406],[0.229,0.224,0.225])
#         ])

#     def __len__(self):
#         return len(self.images)

#     def __getitem__(self, idx):
#         img_path = self.images[idx]
#         mask_path = self.mask_dir / (img_path.stem + ".png")

#         img = Image.open(img_path).convert("RGB")
#         mask = Image.open(mask_path).convert("L")  # grayscale

#         img = self.tf_img(img)
#         mask = mask.resize((self.size, self.size), resample=Image.NEAREST)
#         mask = np.array(mask, dtype=np.float32) / 255.0
#         mask = torch.from_numpy(mask).unsqueeze(0)  # [1,H,W]

#         return img, mask

# # =========================
# # Model: U-Net small
# # =========================
# class ConvBlock(nn.Module):
#     def __init__(self, in_ch, out_ch):
#         super().__init__()
#         self.net = nn.Sequential(
#             nn.Conv2d(in_ch, out_ch, 3, padding=1),
#             nn.BatchNorm2d(out_ch),
#             nn.ReLU(inplace=True),
#             nn.Conv2d(out_ch, out_ch, 3, padding=1),
#             nn.BatchNorm2d(out_ch),
#             nn.ReLU(inplace=True)
#         )
#     def forward(self, x):
#         return self.net(x)

# class UNetSmall(nn.Module):
#     def __init__(self, in_ch=3, out_ch=1, base=32):
#         super().__init__()
#         self.enc1 = ConvBlock(in_ch, base)
#         self.enc2 = ConvBlock(base, base*2)
#         self.enc3 = ConvBlock(base*2, base*4)
#         self.enc4 = ConvBlock(base*4, base*8)
#         self.pool = nn.MaxPool2d(2)
#         self.up4 = nn.ConvTranspose2d(base*8, base*4, 2, stride=2)
#         self.dec4 = ConvBlock(base*8, base*4)
#         self.up3 = nn.ConvTranspose2d(base*4, base*2, 2, stride=2)
#         self.dec3 = ConvBlock(base*4, base*2)
#         self.up2 = nn.ConvTranspose2d(base*2, base, 2, stride=2)
#         self.dec2 = ConvBlock(base*2, base)
#         self.outc = nn.Conv2d(base, out_ch, 1)

#     def forward(self, x):
#         e1 = self.enc1(x)
#         e2 = self.enc2(self.pool(e1))
#         e3 = self.enc3(self.pool(e2))
#         e4 = self.enc4(self.pool(e3))

#         d4 = self.up4(e4)
#         d4 = self.dec4(torch.cat([d4, e3], dim=1))
#         d3 = self.up3(d4)
#         d3 = self.dec3(torch.cat([d3, e2], dim=1))
#         d2 = self.up2(d3)
#         d2 = self.dec2(torch.cat([d2, e1], dim=1))
#         out = self.outc(d2)
#         return out

# # =========================
# # Loss & Metrics
# # =========================
# class DiceLoss(nn.Module):
#     def __init__(self, smooth=1.):
#         super().__init__()
#         self.smooth = smooth
#     def forward(self, logits, targets):
#         probs = torch.sigmoid(logits)
#         num = 2*(probs*targets).sum(dim=(1,2,3)) + self.smooth
#         den = (probs*probs).sum(dim=(1,2,3)) + (targets*targets).sum(dim=(1,2,3)) + self.smooth
#         dice = num/den
#         return 1 - dice.mean()

# def iou_score(logits, targets, thr=0.5):
#     probs = torch.sigmoid(logits)
#     preds = (probs >= thr).float()
#     inter = (preds*targets).sum(dim=(1,2,3))
#     union = (preds+targets - preds*targets).sum(dim=(1,2,3)) + 1e-6
#     return (inter/union).mean().item()

# # =========================
# # Train / Validate
# # =========================
# def train_one_epoch(model, dl, opt, bce, dice, device):
#     model.train()
#     losses = []
#     for x,y in tqdm(dl, desc="train", leave=False):
#         x,y = x.to(device), y.to(device)
#         logits = model(x)
#         loss = 0.5*bce(logits, y) + 0.5*dice(logits, y)
#         opt.zero_grad(); loss.backward(); opt.step()
#         losses.append(loss.item())
#     return np.mean(losses)

# @torch.no_grad()
# def validate(model, dl, bce, dice, device):
#     model.eval()
#     losses, ious = [], []
#     for x,y in tqdm(dl, desc="val", leave=False):
#         x,y = x.to(device), y.to(device)
#         logits = model(x)
#         loss = 0.5*bce(logits, y) + 0.5*dice(logits, y)
#         losses.append(loss.item())
#         ious.append(iou_score(logits, y))
#     return np.mean(losses), np.mean(ious)

# # =========================
# # Main
# # =========================
# def main():
#     set_seed(42)
#     cfg = yaml.safe_load(open("configs/fruit_defect.yaml","r",encoding="utf-8"))["seg"]

#     train_ds = SegDataset(cfg["train_images"], cfg["train_masks"], size=cfg["img_size"], augment=True)
#     val_ds   = SegDataset(cfg["val_images"], cfg["val_masks"], size=cfg["img_size"], augment=False)

#     train_dl = DataLoader(train_ds, batch_size=cfg["batch_size"], shuffle=True)
#     val_dl   = DataLoader(val_ds,   batch_size=cfg["batch_size"], shuffle=False)

#     device = "cuda" if torch.cuda.is_available() else "cpu"
#     model = UNetSmall().to(device)

#     bce = nn.BCEWithLogitsLoss()
#     dice = DiceLoss()
#     opt = torch.optim.AdamW(model.parameters(), lr=cfg["lr"], weight_decay=cfg["weight_decay"])

#     best_iou, best_state = -1, None
#     for ep in range(1, cfg["epochs"]+1):
#         tr_loss = train_one_epoch(model, train_dl, opt, bce, dice, device)
#         va_loss, va_iou = validate(model, val_dl, bce, dice, device)
#         print(f"Epoch {ep}/{cfg['epochs']}: train_loss={tr_loss:.4f}, val_loss={va_loss:.4f}, val_IoU={va_iou:.4f}")
#         if va_iou > best_iou:
#             best_iou = va_iou
#             best_state = {k: v.cpu() for k,v in model.state_dict().items()}

#     out_w = Path(cfg["best_weights"])
#     out_w.parent.mkdir(parents=True, exist_ok=True)
#     torch.save(best_state, out_w)
#     print(f"✅ Saved best model to {out_w}, best IoU={best_iou:.4f}")

# if __name__ == "__main__":
#     main()
