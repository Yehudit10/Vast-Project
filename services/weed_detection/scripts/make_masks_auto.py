# scripts/make_masks_auto.py
import os
import cv2
import numpy as np

IM_DIR = "data/images"
MASK_DIR = "data/masks"
os.makedirs(MASK_DIR, exist_ok=True)

def exg_mask(bgr):
    b, g, r = cv2.split(bgr.astype(np.float32))
    # Simple Excess Green: ExG = 2G - R - B
    exg = 2*g - r - b
    exg = cv2.normalize(exg, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    # Automatic threshold (Otsu)
    thr_val, thr = cv2.threshold(exg, 0, 255, cv2.THRESH_BINARY+cv2.THRESH_OTSU)
    # Cleanup: opening/closing
    kernel = np.ones((3,3), np.uint8)
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN, kernel, iterations=1)
    thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, kernel, iterations=1)
    return (thr > 0).astype(np.uint8)  # 0/1

def process_one(path):
    bgr = cv2.imread(path)
    if bgr is None:
        print(f"[warn] cannot read: {path}")
        return
    mask01 = exg_mask(bgr)          # [H,W] uint8 0/1
    out = (mask01 * 255).astype(np.uint8)
    name = os.path.splitext(os.path.basename(path))[0] + ".png"
    cv2.imwrite(os.path.join(MASK_DIR, name), out)

def main():
    for fn in os.listdir(IM_DIR):
        if fn.lower().endswith((".jpg",".jpeg",".png",".bmp","tif","tiff")):
            process_one(os.path.join(IM_DIR, fn))
    print("done. masks saved to:", MASK_DIR)

if __name__ == "__main__":
    main()
