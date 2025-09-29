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

def classify_ripeness(feat, thr):
    # --- thresholds 
    hmin = float(thr.get("unripe_h_min", 30))
    hmax = float(thr.get("unripe_h_max", 95))
    min_s = float(thr.get("unripe_min_s", 25))   
    br_th = float(thr.get("overripe_brown_ratio", 0.12))
    v_dark = float(thr.get("overripe_min_v", 55))

    mean_h = float(getattr(feat, "mean_h"))
    mean_s = float(getattr(feat, "mean_s", 0.0))
    mean_v = float(getattr(feat, "mean_v"))
    brown_ratio = float(getattr(feat, "brown_ratio"))

    if brown_ratio >= br_th or (brown_ratio >= br_th*0.7 and mean_v <= v_dark and not (hmin <= mean_h <= hmax)):
        return "Overripe"

    if (hmin <= mean_h <= hmax) and (mean_s >= min_s):
        return "Unripe"

    return "Ripe"
