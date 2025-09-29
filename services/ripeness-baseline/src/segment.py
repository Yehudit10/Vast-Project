import cv2 as cv
import numpy as np

def _mask_apple(img):
    hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
    lower = np.array([0, 30, 30], np.uint8)
    upper = np.array([179, 255, 255], np.uint8)
    mask = cv.inRange(hsv, lower, upper)
    mask = cv.medianBlur(mask, 5)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, cv.getStructuringElement(cv.MORPH_ELLIPSE,(9,9)))
    return mask

def _mask_banana(img):
    hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
    lower = np.array([18, 60, 40], np.uint8)
    upper = np.array([45, 255, 255], np.uint8)
    mask_yellow = cv.inRange(hsv, lower, upper)
    lower_brown = np.array([5, 50, 20], np.uint8)
    upper_brown = np.array([25, 255, 200], np.uint8)
    mask_brown = cv.inRange(hsv, lower_brown, upper_brown)
    mask = cv.bitwise_or(mask_yellow, mask_brown)
    mask = cv.medianBlur(mask, 5)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, cv.getStructuringElement(cv.MORPH_ELLIPSE,(9,9)))
    return mask

def _mask_orange(img):
    hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
    lower = np.array([8, 60, 40], np.uint8)
    upper = np.array([28, 255, 255], np.uint8)
    mask = cv.inRange(hsv, lower, upper)
    mask = cv.medianBlur(mask, 5)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, cv.getStructuringElement(cv.MORPH_ELLIPSE,(9,9)))
    return mask

def segment_fruit(img, fruit):
    """
    Segments fruit in HSV, removes low-sat/dark background,
    removes green leaf pixels, cleans noise, and keeps largest blob.
    Returns: (fruit_mask_uint8, leaf_ratio_float)
    """
    img = img.astype(np.float32)
    for c in range(3):
        img[..., c] *= (img.mean() / (img[..., c].mean() + 1e-6))
    img = np.clip(img, 0, 255).astype(np.uint8)

    lab = cv.cvtColor(img, cv.COLOR_BGR2LAB)
    l, a, b = cv.split(lab)
    clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    img = cv.cvtColor(cv.merge([l, a, b]), cv.COLOR_LAB2BGR)


    hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
    h, s, v = cv.split(hsv)

    if fruit == "banana":
        mask = _mask_banana(img)
    elif fruit == "orange":
        mask = _mask_orange(img)
    else:
        mask = _mask_apple(img)
    green_mask = ((h >= 40) & (h <= 85) & (s >= 100)).astype(np.uint8) * 255

    denom = max(1, int((mask > 0).sum()))
    leaf_ratio = float((green_mask > 0).sum()) / float(denom)

    fruit_mask = cv.bitwise_and(mask, cv.bitwise_not(green_mask))

    kernel = np.ones((5, 5), np.uint8)
    fruit_mask = cv.morphologyEx(fruit_mask, cv.MORPH_OPEN, kernel, iterations=2)
    fruit_mask = cv.morphologyEx(fruit_mask, cv.MORPH_CLOSE, kernel, iterations=2)

    num_labels, labels, stats, _ = cv.connectedComponentsWithStats(fruit_mask, 8, cv.CV_32S)
    if num_labels <= 1:
        return np.zeros_like(fruit_mask), 0.0
    largest = 1 + np.argmax(stats[1:, cv.CC_STAT_AREA])
    out = (labels == largest).astype(np.uint8) * 255
    return out, leaf_ratio
