import cv2 as cv
import numpy as np

def segment_fruit(img_bgr):
    """
    Segments fruit in HSV, removes low-sat/dark background,
    removes green leaf pixels, cleans noise, and keeps largest blob.
    Returns: (fruit_mask_uint8, leaf_ratio_float)
    """
    hsv = cv.cvtColor(img_bgr, cv.COLOR_BGR2HSV)
    h, s, v = cv.split(hsv)

    # בסיס: אזור "פרי" כללי (מונע רקעים דלים/חשוכים)
    base_mask = cv.inRange(hsv, (0, 40, 50), (179, 255, 255))  # uint8 {0,255}

    # זיהוי עלה ירוק: Hue ∈ [40,85], Saturation גבוהה כדי להימנע מלבן/רקע
    green_mask = ((h >= 40) & (h <= 85) & (s >= 100)).astype(np.uint8) * 255

    # יחס עלה (מתוך אזור הפרי הראשוני)
    denom = max(1, int((base_mask > 0).sum()))
    leaf_ratio = float((green_mask > 0).sum()) / float(denom)

    # מסכת פרי ללא עלה
    fruit_mask = cv.bitwise_and(base_mask, cv.bitwise_not(green_mask))

    # ניקוי מורפולוגי
    kernel = np.ones((5, 5), np.uint8)
    fruit_mask = cv.morphologyEx(fruit_mask, cv.MORPH_OPEN, kernel, iterations=2)
    fruit_mask = cv.morphologyEx(fruit_mask, cv.MORPH_CLOSE, kernel, iterations=2)

    # לשמור רק את ה-blob הגדול
    num_labels, labels, stats, _ = cv.connectedComponentsWithStats(fruit_mask, 8, cv.CV_32S)
    if num_labels <= 1:
        return np.zeros_like(fruit_mask), 0.0
    largest = 1 + np.argmax(stats[1:, cv.CC_STAT_AREA])
    out = (labels == largest).astype(np.uint8) * 255
    return out, leaf_ratio
