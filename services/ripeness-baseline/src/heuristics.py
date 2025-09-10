from dataclasses import dataclass
import numpy as np
import cv2 as cv

@dataclass
class Features:
    mean_h: float
    mean_s: float
    mean_v: float
    lap_var: float
    brown_ratio: float
    mask_cov: float

def _laplacian_variance(gray: np.ndarray, mask: np.ndarray) -> float:
    lap = cv.Laplacian(gray, cv.CV_64F)
    m = mask.astype(bool)
    return float(np.var(lap[m])) if np.any(m) else 0.0

def _brown_ratio(h: np.ndarray, v: np.ndarray, mask: np.ndarray) -> float:
    m = mask.astype(bool)
    brown_hue = ((h >= 10) & (h <= 30)) & m
    dark = (v < 50) & m
    tot = np.count_nonzero(m)
    if tot == 0: return 0.0
    return float(np.count_nonzero(brown_hue | dark) / tot)

def compute_features(img_bgr: np.ndarray, mask: np.ndarray) -> Features:
    hsv = cv.cvtColor(img_bgr, cv.COLOR_BGR2HSV)
    h, s, v = cv.split(hsv)
    m = mask.astype(bool)

    mean_h = float(np.mean(h[m])) if np.any(m) else 0.0
    mean_s = float(np.mean(s[m])) if np.any(m) else 0.0
    mean_v = float(np.mean(v[m])) if np.any(m) else 0.0

    gray = cv.cvtColor(img_bgr, cv.COLOR_BGR2GRAY)
    lap_var = _laplacian_variance(gray, mask)
    brown_ratio = _brown_ratio(h, v, mask)

    mask_cov = float(np.count_nonzero(m) / (img_bgr.shape[0] * img_bgr.shape[1]))
    return Features(mean_h, mean_s, mean_v, lap_var, brown_ratio, mask_cov)

def classify_ripeness(f: Features, thr: dict) -> str:
    # Overripe אם כהה/חום מדי או בהירות נמוכה
    if f.brown_ratio > thr["overripe_brown_ratio"] or f.mean_v < thr["overripe_min_v"]:
        return "Overripe"
    # Unripe אם Hue ירקרק יחסית
    if thr["unripe_h_min"] <= f.mean_h <= thr["unripe_h_max"]:
        return "Unripe"
    # אחרת – Ripe
    return "Ripe"
