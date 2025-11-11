# agri_baseline/src/pipeline/utils.py
# Max line length: 100

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Tuple

import cv2
import numpy as np


class ImageLoadError(Exception):
    """Raised when an image cannot be decoded or is empty."""


def load_image(path: str | Path) -> Tuple[np.ndarray, int, int]:
    """
    Load an image from disk as BGR uint8 and return (img, width, height).

    Rules:
    - Always read as color to ensure 3 channels (BGR).
    - Raise FileNotFoundError if the path doesn't exist.
    - Raise ImageLoadError if decode fails or the image is empty.
    - Convert dtype to uint8 if needed.
    - Normalize channel count: grayscale -> BGR, BGRA -> BGR.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {p.resolve()}")

    # Always load as color to ensure 3 channels (BGR)
    img = cv2.imread(str(p), cv2.IMREAD_COLOR)
    if img is None or img.size == 0:
        raise ImageLoadError(f"Failed to decode image (or empty): {p.resolve()}")

    if img.dtype != np.uint8:
        img = cv2.convertScaleAbs(img)

    # Guard channel count (should be 3 after IMREAD_COLOR, but just in case)
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    h, w = img.shape[:2]
    return img, w, h


def image_id_from_path(path: str | Path) -> str:
    p = Path(path)
    digest = hashlib.sha1(str(p.resolve()).encode()).hexdigest()[:16]
    return f"{p.stem}_{digest}"


def clamp_bbox(x: int, y: int, w: int, h: int, W: int, H: int) -> Tuple[int, int, int, int]:
    x = max(0, min(x, W - 1))
    y = max(0, min(y, H - 1))
    w = max(1, min(w, W - x))
    h = max(1, min(h, H - y))
    return x, y, w, h
