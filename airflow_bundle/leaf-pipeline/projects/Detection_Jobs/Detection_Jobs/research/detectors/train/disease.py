import cv2
import numpy as np

from ...agri_baseline.src.detectors.base import Detection
from ..pipeline import config


class DiseaseDetector:
    """
    Improved disease detector:
    - Leaf mask (HSV/LAB) to isolate plant tissue.
    - Candidate lesion detection:
        1) Yellow/Brown in HSV (stress/necrosis).
        2) Dark + Brown in LAB (low L, high b).
    - Noise cleaning and merging.
    - Shape filtering by circularity (detect "spots").
    - Confidence weighted by darkness, saturation, and circularity.
    """

    name = "disease"

    # HSV thresholds for yellow/brown (tunable)
    HSV_YELLOW = ((10, 50, 40), (45, 255, 255))
    HSV_BROWN1 = ((0, 80, 30), (10, 255, 200))
    HSV_BROWN2 = ((160, 80, 30), (179, 255, 200))

    # LAB thresholds for dark/brown lesions (tunable)
    LAB_L_MAX_DARK = 145   # Lower L means darker
    LAB_B_MIN_BROWN = 135  # Higher b means more yellow/brown

    # Shape filtering
    MIN_CIRCULARITY = 0.22  # 4πA/P^2; range 0..1
    MAX_ASPECT_RATIO = 2.2  # Avoid elongated regions
    DILATE_MERGE_RADIUS = 4

    def __init__(self):
        # Minimum area from config (fallback to default if missing)
        self.min_area = int(getattr(config, "MIN_BBOX_AREA", 60))

    def run(self, bgr_image: np.ndarray) -> list[Detection]:
        h, w = bgr_image.shape[:2]

        # ---------- 1) Leaf isolation ----------
        hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
        lab = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2LAB)
        H, S, V = cv2.split(hsv)
        L, A, B = cv2.split(lab)

        # Green mask in HSV (broad range for leaf tissue)
        green1 = cv2.inRange(hsv, (35, 30, 30), (85, 255, 255))
        green2 = cv2.inRange(hsv, (25, 25, 40), (95, 255, 255))
        leaf_mask = cv2.bitwise_or(green1, green2)

        # Contrast enhancement with CLAHE on L channel
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        L_eq = clahe.apply(L)

        # Basic cleaning of leaf mask
        leaf_mask = cv2.medianBlur(leaf_mask, 5)
        leaf_mask = cv2.morphologyEx(
            leaf_mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1
        )

        # ---------- 2) Lesion candidates ----------
        # (a) Yellow/Brown in HSV
        yellow = cv2.inRange(hsv, self.HSV_YELLOW[0], self.HSV_YELLOW[1])
        brown1 = cv2.inRange(hsv, self.HSV_BROWN1[0], self.HSV_BROWN1[1])
        brown2 = cv2.inRange(hsv, self.HSV_BROWN2[0], self.HSV_BROWN2[1])
        hsv_spots = cv2.bitwise_or(yellow, cv2.bitwise_or(brown1, brown2))

        # (b) Dark + Brownish in LAB
        dark = cv2.threshold(L_eq, self.LAB_L_MAX_DARK, 255, cv2.THRESH_BINARY_INV)[1]
        brownish = cv2.threshold(B, self.LAB_B_MIN_BROWN, 255, cv2.THRESH_BINARY)[1]
        lab_spots = cv2.bitwise_and(dark, brownish)

        # Combine HSV and LAB candidates, restricted to leaf mask
        candidates = cv2.bitwise_or(hsv_spots, lab_spots)
        candidates = cv2.bitwise_and(candidates, leaf_mask)

        # ---------- 3) Cleaning & merging ----------
        candidates = cv2.medianBlur(candidates, 3)
        candidates = cv2.morphologyEx(
            candidates, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1
        )

        # Dilate slightly to merge nearby spots
        if self.DILATE_MERGE_RADIUS > 0:
            k = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE,
                (2 * self.DILATE_MERGE_RADIUS + 1, 2 * self.DILATE_MERGE_RADIUS + 1),
            )
            candidates = cv2.dilate(candidates, k, iterations=1)

        # ---------- 4) Contours & filtering ----------
        cnts, _ = cv2.findContours(candidates, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dets = []
        for c in cnts:
            area = cv2.contourArea(c)
            if area < self.min_area:
                continue

            x, y, bw, bh = cv2.boundingRect(c)

            # Circularity: 4πA / P^2
            perim = cv2.arcLength(c, True)
            circularity = (4.0 * np.pi * area / (perim ** 2 + 1e-6)) if perim > 0 else 0.0
            if circularity < self.MIN_CIRCULARITY:
                continue

            # Aspect ratio filtering
            ar = max(bw, bh) / (min(bw, bh) + 1e-6)
            if ar > self.MAX_ASPECT_RATIO:
                continue

            # Extract subregion for scoring
            hsv_box = hsv[y : y + bh, x : x + bw]
            lab_box = lab[y : y + bh, x : x + bw]

            Lb = lab_box[:, :, 0].astype(np.float32)
            Sb = hsv_box[:, :, 1].astype(np.float32)

            # Darkness score (lower L → higher score)
            dark_score = np.clip((180.0 - float(np.mean(Lb))) / 180.0, 0.0, 1.0)
            # Saturation score (higher S → higher score)
            sat_score = np.clip(float(np.mean(Sb)) / 255.0, 0.0, 1.0)

            # Final weighted confidence
            conf = 0.45 * dark_score + 0.35 * sat_score + 0.20 * np.clip(circularity, 0.0, 1.0)
            conf = float(np.clip(conf, 0.0, 1.0))

            dets.append(
                Detection(
                    label="disease_spot",
                    confidence=conf,
                    x=int(x),
                    y=int(y),
                    w=int(bw),
                    h=int(bh),
                    area=int(area),
                )
            )

        # ---------- 5) Merge overlapping boxes ----------
        dets = self._merge_overlaps(dets, iou_thresh=0.5)
        return dets

    # ---------- IoU helper ----------
    @staticmethod
    def _iou(a, b):
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.w, a.y + a.h
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.w, b.y + b.h
        inter_x1, inter_y1 = max(ax1, bx1), max(ay1, by1)
        inter_x2, inter_y2 = min(ax2, bx2), min(ay2, by2)
        iw, ih = max(0, inter_x2 - inter_x1), max(0, inter_y2 - inter_y1)
        inter = iw * ih
        if inter == 0:
            return 0.0
        area_a = a.w * a.h
        area_b = b.w * b.h
        return inter / float(area_a + area_b - inter + 1e-6)

    def _merge_overlaps(self, dets, iou_thresh=0.5):
        if not dets:
            return dets
        dets = sorted(dets, key=lambda d: d.confidence, reverse=True)
        kept = []
        while dets:
            base = dets.pop(0)
            to_merge = [base]
            remain = []
            for d in dets:
                if self._iou(base, d) >= iou_thresh:
                    to_merge.append(d)
                else:
                    remain.append(d)
            dets = remain

            # Merge into one bounding box
            xs = [d.x for d in to_merge]
            ys = [d.y for d in to_merge]
            x2s = [d.x + d.w for d in to_merge]
            y2s = [d.y + d.h for d in to_merge]
            x = int(min(xs))
            y = int(min(ys))
            w = int(max(x2s) - x)
            h = int(max(y2s) - y)

            # Average confidence
            conf = float(np.mean([d.confidence for d in to_merge]))
            area = int(w * h)
            kept.append(
                Detection(
                    label="disease_spot",
                    confidence=conf,
                    x=x,
                    y=y,
                    w=w,
                    h=h,
                    area=area,
                )
            )
        return kept
