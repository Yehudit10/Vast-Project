from __future__ import annotations
from typing import Dict, List, Tuple
from pathlib import Path
import numpy as np
from ultralytics import YOLO
import cv2

# ==============================================================
#                    STRUCTURE AND MAPPINGS
# ==============================================================

Detection = Tuple[int, str, float, int, int, int, int]

RAW_ID2NAME: Dict[int, str] = {
    0: "Agri equipment", 1: "Agri infra", 2: "Buildings", 3: "Rail",
    4: "Vessels", 5: "Aviation", 6: "Construction site", 7: "Cranes",
    8: "Towers", 9: "Vehicles", 10: "Containers", 11: "Yards",
}

PALETTE = {
    (210, 180, 140): (12, "Bareland"),
    (152, 251, 152): (13, "Rangeland"),
    (128, 128, 128): (14, "Developed space"),
    (255, 255, 255): (15, "Road"),
    (0, 100, 0): (16, "Tree"),
    (30, 144, 255): (17, "Water"),
    (255, 215, 0): (18, "Agriculture"),
    (178, 34, 34): (19, "Buildings"),
    (0, 0, 0): (20, "Other"),
}

MODEL_PRIORITY = {
    "vehicles": "yolo", "cranes": "yolo", "towers": "yolo", "containers": "yolo",
    "yards": "yolo", "buildings": "yolo",
    "road": "mask", "tree": "mask", "water": "mask", "agriculture": "mask",
    "bareland": "mask", "rangeland": "mask", "developed space": "mask", "other": "mask",
}

# ==============================================================
#                      YOLO MODEL WRAPPER
# ==============================================================

class ModelWrapper:
    def __init__(self, weights_path: str = "best.pt", conf: float = 0.25, iou: float = 0.45):
        wp = Path(weights_path)
        if not wp.exists():
            raise FileNotFoundError(f"Weights not found: {wp.resolve()}")
        self.model = YOLO(str(wp))
        self.id2name = {int(i): str(n) for i, n in self.model.names.items()} if hasattr(self.model, "names") else RAW_ID2NAME
        self.conf = conf
        self.iou = iou

    def labels(self) -> Dict[int, str]:
        return {i: n for i, n in self.id2name.items()}

    def predict(self, image: Image.Image) -> List[Detection]:
        results = self.model.predict(source=np.array(image), conf=self.conf, iou=self.iou, verbose=False)
        dets: List[Detection] = []
        for r in results:
            if r.boxes is None:
                continue
            xyxy = r.boxes.xyxy.cpu().numpy()
            confs = r.boxes.conf.cpu().numpy()
            clss = r.boxes.cls.cpu().numpy().astype(int)
            for (x1, y1, x2, y2), conf, cls in zip(xyxy, confs, clss):
                name = self.id2name.get(int(cls), f"class_{cls}")
                dets.append((int(cls), name, float(conf), int(x1), int(y1), int(x2), int(y2)))
        return dets


# ==============================================================
#                     SEGFORMER MASK PROCESSING
# ==============================================================

def color_mask_to_class_map(mask_rgb: Image.Image) -> np.ndarray:
    mask = np.array(mask_rgb.convert("RGB"))
    class_map = np.zeros(mask.shape[:2], dtype=np.uint8)
    for color, (cid, _) in PALETTE.items():
        match = np.all(mask == color, axis=-1)
        class_map[match] = cid
    return class_map


def mask_to_detections(mask_rgb: Image.Image) -> List[Detection]:
    mask = color_mask_to_class_map(mask_rgb)
    dets: List[Detection] = []
    GENERAL_MIN = 100
    ROAD_MIN = 1000
    for cid in np.unique(mask):
        if cid == 0:
            continue
        binary = (mask == cid).astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        _, cname = next(v for v in PALETTE.values() if v[0] == cid)
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            area = w * h
            if cname.lower() == "road" and area < ROAD_MIN:
                continue
            if area < GENERAL_MIN:
                continue
            dets.append((cid, cname, 1.0, x, y, x + w, y + h))
    return dets


# ==============================================================
#                        MERGING LOGIC (Smart)
# ==============================================================

def iou(a: Detection, b: Detection) -> float:
    xA, yA = max(a[3], b[3]), max(a[4], b[4])
    xB, yB = min(a[5], b[5]), min(a[6], b[6])
    inter = max(0, xB - xA) * max(0, yB - yA)
    areaA = (a[5] - a[3]) * (a[6] - a[4])
    areaB = (b[5] - b[3]) * (b[6] - b[4])
    union = areaA + areaB - inter
    return inter / union if union > 0 else 0.0


def merge_detections(yolo_dets: List[Detection], mask_dets: List[Detection], iou_thresh=0.4) -> List[Detection]:
    final = list(yolo_dets)

    for md in mask_dets:
        m_name = md[1].lower()
        x1, y1, x2, y2 = md[3:7]
        area = (x2 - x1) * (y2 - y1)

        if m_name == "tree" and area > 10000: 
            md = (md[0], "Forest", md[2], x1, y1, x2, y2)

        overlap = False

        for yd in list(final):
            y_name = yd[1].lower()
            ov = iou(md, yd)
            if ov > iou_thresh:
                if y_name in ("building", "buildings") and m_name != "building":
                    final.remove(yd)
                    continue

                y_pri = MODEL_PRIORITY.get(y_name, "yolo")
                m_pri = MODEL_PRIORITY.get(m_name, "mask")
                if m_pri == "mask" and y_pri == "yolo":
                    final.remove(yd)
                    final.append(md)
                    overlap = True
                    break
                else:
                    overlap = True

        if not overlap:
            final.append(md)

    return final
