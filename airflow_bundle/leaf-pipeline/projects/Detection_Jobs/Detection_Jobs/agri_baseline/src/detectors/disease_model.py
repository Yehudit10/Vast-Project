# agri_baseline/src/detectors/disease_model.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np
import torch
import albumentations as A
from albumentations.pytorch import ToTensorV2

from agri_baseline.src.detectors.cnn_multi_classifier import build_multi_model
from agri_baseline.src.detectors.train.dictionary import CLASS_MAPPING


@dataclass
class Detection:
    """Simple container for a single detection box."""
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    confidence: float
    label: str = "disease"

    @property
    def area(self) -> int:
        x, y, w, h = self.bbox
        return int(w * h)


def _ensure_bgr_uint8(img: np.ndarray) -> np.ndarray:
    """
    Normalize any input image to BGR uint8 with 3 channels.
    Prevents cvtColor from crashing with color.simd_helpers.hpp:94.

    Rules:
    - None / empty -> ValueError
    - GRAY (H,W) -> BGR
    - BGRA (H,W,4) -> BGR
    - dtype != uint8 -> convert to uint8 (clip to [0..255])
    """
    if img is None or getattr(img, "size", 0) == 0:
        raise ValueError("DiseaseDetector: empty/None image given")

    # If grayscale -> convert to BGR
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    # If BGRA -> drop alpha
    elif img.ndim == 3 and img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # Validate shape now
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"DiseaseDetector: unexpected image shape {img.shape}")

    # Ensure uint8
    if img.dtype != np.uint8:
        img = np.clip(img, 0, 255).astype(np.uint8)

    # Ensure non-zero size
    h, w = img.shape[:2]
    if h == 0 or w == 0:
        raise ValueError("DiseaseDetector: zero-sized image")

    return img


class DiseaseDetector:
    """
    CNN-based disease classifier.
    - Normalizes input to BGR uint8 (3-ch) to avoid OpenCV color conversion crashes.
    - Converts BGR->RGB before Albumentations (Normalize + ToTensorV2).
    """

    name = "disease"

    def __init__(self, model_path: str = "models/cnn_multi_stage3.pth", device: str | None = None) -> None:
        # choose device
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        # build model according to class mapping
        self.classes = sorted(set(CLASS_MAPPING.values()))
        self.model = build_multi_model(num_classes=len(self.classes)).to(self.device)

        # load trained weights
        state = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state)
        self.model.eval()

        # same validation transforms used in training
        self.transform = A.Compose(
            [
                A.Resize(224, 224),
                A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
                ToTensorV2(),
            ]
        )

    def run(self, img: np.ndarray) -> List[Detection]:
        """
        Run the classifier on a single image.
        :param img: np.ndarray from OpenCV (BGR or GRAY/BGRA/float) — any shape/dtype.
        :return: list with a single full-frame Detection carrying predicted label/confidence.
        """
        # 1) Normalize input so cvtColor is safe
        img = _ensure_bgr_uint8(img)

        # 2) Convert to RGB for the model pipeline
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # 3) Albumentations -> tensor
        aug = self.transform(image=img_rgb)
        tensor = aug["image"].unsqueeze(0).to(self.device)

        # 4) Model inference
        with torch.no_grad():
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1)[0]
            conf_t, cls_t = torch.max(probs, dim=0)

        label = self.classes[cls_t.item()]
        confidence = float(conf_t.item())

        # 5) Return a single detection that spans the whole image (classifier)
        h, w = img.shape[:2]
        det = Detection(bbox=(0, 0, w, h), confidence=confidence, label=label)
        return [det]
