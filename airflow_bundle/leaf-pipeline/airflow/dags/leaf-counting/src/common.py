from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}

def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMG_EXTS

def iter_images(inp: Path):
    p = Path(inp)
    if p.is_file() and is_image(p):
        yield p
    elif p.is_dir():
        for q in sorted(p.rglob("*")):
            if q.is_file() and is_image(q):
                yield q

def ensure_dir(p: Path) -> Path:
    Path(p).mkdir(parents=True, exist_ok=True)
    return Path(p)

def draw_boxes(img_bgr: np.ndarray, boxes, color=(0,255,0), thickness=2):
    h, w = img_bgr.shape[:2]
    out = img_bgr.copy()
    for (x1,y1,x2,y2,conf,cls_id) in boxes:
        x1 = max(0, min(w-1, int(x1)))
        y1 = max(0, min(h-1, int(y1)))
        x2 = max(0, min(w-1, int(x2)))
        y2 = max(0, min(h-1, int(y2)))
        cv2.rectangle(out, (x1,y1), (x2,y2), color, thickness)
        label = f"{int(cls_id)}:{conf:.2f}"
        cv2.putText(out, label, (x1, max(0, y1-5)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return out