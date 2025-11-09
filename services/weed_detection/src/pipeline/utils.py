# /src/pipeline/utils.py
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np


def load_image(path: str | Path):
    p = Path(path)
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Failed to load image: {p}")
    img = np.ascontiguousarray(img)
    h, w = img.shape[:2]
    return img, w, h  # זה הפורמט שה-Runner שלך מצפה לו

def image_id_from_path(p: str | Path) -> str:
    return Path(p).stem

def clamp_bbox(x: int, y: int, w: int, h: int, W: int, H: int):
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(0, min(w, W - x))
    h = max(0, min(h, H - y))
    return x, y, w, h
