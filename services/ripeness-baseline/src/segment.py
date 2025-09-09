import cv2 as cv
import numpy as np

def segment_fruit(img_bgr):
    """סגמנטציה ב-HSV: מסיר רקעים דלי-רוויה/חשוכים, מנקה ברעש מורפולוגי, ובוחר קומפוננטה הכי גדולה."""
    hsv = cv.cvtColor(img_bgr, cv.COLOR_BGR2HSV)
    # טווח "כללי" לפרי: רוויה מעל 40 וערך מעל 50 (מסיר רקעים דלים/חשוכים)
    mask = cv.inRange(hsv, (0, 40, 50), (179, 255, 255))

    kernel = np.ones((5,5), np.uint8)
    mask = cv.morphologyEx(mask, cv.MORPH_OPEN, kernel, iterations=2)
    mask = cv.morphologyEx(mask, cv.MORPH_CLOSE, kernel, iterations=2)

    # בחירת ה-blob הגדול ביותר
    num_labels, labels, stats, _ = cv.connectedComponentsWithStats(mask, 8, cv.CV_32S)
    if num_labels <= 1:
        return np.zeros_like(mask)
    largest = 1 + np.argmax(stats[1:, cv.CC_STAT_AREA])
    out = (labels == largest).astype(np.uint8) * 255
    return out
