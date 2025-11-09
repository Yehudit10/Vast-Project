# /src/detectors/disease_model.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple, Union
import os
import numpy as np
import torch
import cv2

# If your import path is different (e.g., src.models.ml_model), update here:
from models.ml_model import MLWeedDetector


@dataclass
class Detection:
    x: float
    y: float
    w: float
    h: float
    area: float
    confidence: float
    label: str = "disease"  # You can change to "weed" if that's the desired name


class DiseaseDetector:
    """
    Flow:
      1) Build a coarse mask
      2) Refine the mask using MLWeedDetector (your MobileNetV3 model)
      3) Convert to detections (bounding boxes) for DB writing
    """

    def __init__(self) -> None:
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # ---- Load weights ----
        weights_env = os.getenv("WEIGHTS_REFINER", "").strip()
        if weights_env:
            weights_path = Path(weights_env)
        else:
            # Smart search inside the models directory
            project_root = Path(__file__).resolve().parents[2]
            models_dir = project_root / "models"
            candidates = [
                models_dir / "weights_refiner.pth",
                models_dir / "mobilenetv3_best.pth",
                models_dir / "best.pth",
                models_dir / "last.pth",
            ]
            found = [p for p in candidates if p.exists()]
            if not found:
                raise FileNotFoundError(
                    f"Could not find weights file. Set WEIGHTS_REFINER or put a weights .pth under {models_dir}"
                )
            weights_path = found[0]

        # MLWeedDetector already handles Resize(224) + ImageNet normalization
        self.refiner = MLWeedDetector(weights_path=str(weights_path), device=str(self.device))

        # ---- Parameters configurable via .env ----
        self.min_component_area = int(os.getenv("MIN_COMPONENT_AREA", "200"))   # Filter out small connected components
        self.min_bbox_area = int(os.getenv("MIN_BBOX_AREA", "150"))             # Filter out small bounding boxes
        self.bin_thresh = int(os.getenv("REFINED_BIN_THRESH", "128"))           # Binarization threshold after refinement
        self.conf_area_norm = float(os.getenv("CONF_AREA_NORM", "10000"))       # Normalize confidence by area
        self.coarse_method = os.getenv("COARSE_METHOD", "OTSU").upper()         # OTSU / HSV_GREEN
        self.max_infer_side = int(os.getenv("MAX_INFER_SIDE", "0"))             # 0 = no global downscale


    # ---------- Main API ----------

    def run(
        self,
        bgr_img: np.ndarray,
        return_mask: bool = False
    ) -> Union[List[Detection], Tuple[np.ndarray, List[Detection]]]:
        """
        :param bgr_img: OpenCV image in BGR format
        :param return_mask: If True, also return the refined mask (uint8 0/255)
        """
        # Ensure contiguous to prevent negative strides
        bgr = np.ascontiguousarray(bgr_img)

        bgr = self._maybe_downscale(bgr)
        coarse = self._make_coarse(bgr)
        # Ensure contiguous before refinement
        coarse = np.ascontiguousarray(coarse)

        refined = self._refine_with_model(bgr, coarse)          # 0..255
        refined_bin = self._binarize(refined, self.bin_thresh)  # 0/255
        refined_bin = self._remove_small(refined_bin, self.min_component_area)

        detections = self._mask_to_detections(refined_bin)

        if return_mask:
            return refined_bin, detections
        return detections

    # ---------- Processing helpers ----------

    def _maybe_downscale(self, bgr: np.ndarray) -> np.ndarray:
        if not self.max_infer_side or self.max_infer_side <= 0:
            return bgr
        h, w = bgr.shape[:2]
        m = max(h, w)
        if m <= self.max_infer_side:
            return bgr
        scale = self.max_infer_side / float(m)
        new_w, new_h = int(w * scale), int(h * scale)
        out = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(out)

    def _make_coarse(self, bgr: np.ndarray) -> np.ndarray:
        """
        Coarse mask:
          - OTSU (default)
          - or HSV_GREEN if COARSE_METHOD=HSV_GREEN
        """
        if self.coarse_method == "HSV_GREEN":
            hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
            # Generic green range; you can calibrate according to your data:
            lower = np.array([35, 40, 20], dtype=np.uint8)
            upper = np.array([85, 255, 255], dtype=np.uint8)
            mask = cv2.inRange(hsv, lower, upper)  # 0/255
            return np.ascontiguousarray(mask)

        # OTSU (default)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return np.ascontiguousarray(mask)

    def _refine_with_model(self, bgr: np.ndarray, coarse: np.ndarray) -> np.ndarray:
        """
        Refinement using your trained model.
        MLWeedDetector.score_mask(bgr, coarse) -> mask 0..255
        """
        # Ensure contiguous to avoid negative strides inside the refiner
        bgr = np.ascontiguousarray(bgr)
        coarse = np.ascontiguousarray(coarse)

        refined = self.refiner.score_mask(bgr, coarse)
        if refined.dtype != np.uint8:
            refined = np.clip(refined, 0, 255).astype(np.uint8)
        return refined

    def _binarize(self, mask: np.ndarray, thresh: int) -> np.ndarray:
        if mask.dtype != np.uint8:
            mask = np.clip(mask, 0, 255).astype(np.uint8)
        _, mask_bin = cv2.threshold(mask, thresh, 255, cv2.THRESH_BINARY)
        return np.ascontiguousarray(mask_bin)

    def _remove_small(self, mask_bin: np.ndarray, min_area: int) -> np.ndarray:
        if min_area <= 1:
            return mask_bin
        m01 = (mask_bin > 0).astype(np.uint8)
        num_labels, labels = cv2.connectedComponents(m01)
        out = np.zeros_like(m01)
        for i in range(1, num_labels):  # 0 = background
            comp = (labels == i)
            if int(comp.sum()) >= min_area:
                out[comp] = 1
        return (out * 255).astype(np.uint8)

    def _mask_to_detections(self, mask_bin: np.ndarray) -> List[Detection]:
        num, labels, stats, _ = cv2.connectedComponentsWithStats(
            (mask_bin > 0).astype(np.uint8), connectivity=8
        )
        dets: List[Detection] = []
        for i in range(1, num):  # 0 = background
            x, y, w, h, area = stats[i]
            if area < self.min_component_area:
                continue
            if (w * h) < self.min_bbox_area:
                continue
            conf = float(min(1.0, area / max(1.0, self.conf_area_norm)))
            dets.append(
                Detection(
                    x=float(x), y=float(y), w=float(w), h=float(h),
                    area=float(area), confidence=conf, label="disease"
                )
            )
        return dets


# # /src/detectors/disease_model.py
# from __future__ import annotations
# from dataclasses import dataclass
# from pathlib import Path
# from typing import List, Tuple, Union, Optional, Dict, Any
# import os
# import uuid
# from datetime import datetime, timezone

# import numpy as np
# import torch
# import cv2
# import requests

# # If your import path is different (e.g., src.models.ml_model), update here:
# from models.ml_model import MLWeedDetector


# @dataclass
# class Detection:
#     x: float
#     y: float
#     w: float
#     h: float
#     area: float
#     confidence: float
#     label: str = "disease"  # You can change to "weed" if that's the desired name


# class DiseaseDetector:
#     """
#     Flow:
#       1) Build a coarse mask
#       2) Refine the mask using MLWeedDetector (your MobileNetV3 model)
#       3) Convert to detections (bounding boxes) for DB writing
#       4) Compute severity from detections and POST JSON alert if severity > threshold
#     """

#     def __init__(self) -> None:
#         self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

#         # ---- Load weights ----
#         weights_env = os.getenv("WEIGHTS_REFINER", "").strip()
#         if weights_env:
#             weights_path = Path(weights_env)
#         else:
#             # Smart search inside the models directory
#             project_root = Path(__file__).resolve().parents[2]
#             models_dir = project_root / "models"
#             candidates = [
#                 models_dir / "weights_refiner.pth",
#                 models_dir / "mobilenetv3_best.pth",
#                 models_dir / "best.pth",
#                 models_dir / "last.pth",
#             ]
#             found = [p for p in candidates if p.exists()]
#             if not found:
#                 raise FileNotFoundError(
#                     f"Could not find weights file. Set WEIGHTS_REFINER or put a weights .pth under {models_dir}"
#                 )
#             weights_path = found[0]

#         # MLWeedDetector already handles Resize(224) + ImageNet normalization
#         self.refiner = MLWeedDetector(weights_path=str(weights_path), device=str(self.device))

#         # ---- Parameters configurable via .env ----
#         self.min_component_area = int(os.getenv("MIN_COMPONENT_AREA", "200"))   # Filter out small connected components
#         self.min_bbox_area = int(os.getenv("MIN_BBOX_AREA", "150"))             # Filter out small bounding boxes
#         self.bin_thresh = int(os.getenv("REFINED_BIN_THRESH", "128"))           # Binarization threshold after refinement
#         self.conf_area_norm = float(os.getenv("CONF_AREA_NORM", "10000"))       # Normalize confidence by area
#         self.coarse_method = os.getenv("COARSE_METHOD", "OTSU").upper()         # OTSU / HSV_GREEN
#         self.max_infer_side = int(os.getenv("MAX_INFER_SIDE", "0"))             # 0 = no global downscale

#         # ---- Alerting (JSON POST) ----
#         self.alert_thresh = float(os.getenv("ALERT_SEVERITY_THRESH", "0.3"))
#         self.alert_url = os.getenv("ALERT_URL", "http://localhost:8090/alerts")
#         self.device_id = os.getenv("DEVICE_ID", "camera-12")
#         self.area_name = os.getenv("AREA_NAME", "") or None  # optional

#     # ---------- Main API ----------

#     def run(
#         self,
#         bgr_img: np.ndarray,
#         return_mask: bool = False,
#         *,
#         # Optional context to include in the alert JSON if available:
#         image_url: Optional[str] = None,
#         lat: Optional[float] = None,
#         lon: Optional[float] = None,
#         alert_type: str = "disease_detected",
#         meta: Optional[Dict[str, Any]] = None,
#     ) -> Union[List[Detection], Tuple[np.ndarray, List[Detection]]]:
#         """
#         :param bgr_img: OpenCV image in BGR format
#         :param return_mask: If True, also return the refined mask (uint8 0/255)
#         :param image_url: Optional image URL for the alert JSON
#         :param lat: Optional latitude for the alert JSON
#         :param lon: Optional longitude for the alert JSON
#         :param alert_type: Alert type string for the alert JSON
#         :param meta: Optional metadata dict to include in the alert JSON
#         """
#         # Ensure contiguous to prevent negative strides
#         bgr = np.ascontiguousarray(bgr_img)

#         bgr = self._maybe_downscale(bgr)
#         coarse = self._make_coarse(bgr)
#         # Ensure contiguous before refinement
#         coarse = np.ascontiguousarray(coarse)

#         refined = self._refine_with_model(bgr, coarse)          # 0..255
#         refined_bin = self._binarize(refined, self.bin_thresh)  # 0/255
#         refined_bin = self._remove_small(refined_bin, self.min_component_area)

#         detections = self._mask_to_detections(refined_bin)

#         # ---- Compute severity from detections and POST JSON if above threshold ----
#         severity = self._severity_from_detections(detections)
#         if severity > self.alert_thresh:
#             # For "confidence" field, we send the same scalar as severity by default.
#             # Replace if you prefer a different definition.
#             self._post_alert_json(
#                 severity=severity,
#                 alert_type=alert_type,
#                 image_url=image_url,
#                 lat=lat,
#                 lon=lon,
#                 confidence=severity,
#                 meta=meta,
#             )

#         if return_mask:
#             return refined_bin, detections
#         return detections

#     # ---------- Processing helpers ----------

#     def _maybe_downscale(self, bgr: np.ndarray) -> np.ndarray:
#         if not self.max_infer_side or self.max_infer_side <= 0:
#             return bgr
#         h, w = bgr.shape[:2]
#         m = max(h, w)
#         if m <= self.max_infer_side:
#             return bgr
#         scale = self.max_infer_side / float(m)
#         new_w, new_h = int(w * scale), int(h * scale)
#         out = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
#         return np.ascontiguousarray(out)

#     def _make_coarse(self, bgr: np.ndarray) -> np.ndarray:
#         """
#         Coarse mask:
#           - OTSU (default)
#           - or HSV_GREEN if COARSE_METHOD=HSV_GREEN
#         """
#         if self.coarse_method == "HSV_GREEN":
#             hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
#             # Generic green range; you can calibrate according to your data:
#             lower = np.array([35, 40, 20], dtype=np.uint8)
#             upper = np.array([85, 255, 255], dtype=np.uint8)
#             mask = cv2.inRange(hsv, lower, upper)  # 0/255
#             return np.ascontiguousarray(mask)

#         # OTSU (default)
#         gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
#         _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
#         return np.ascontiguousarray(mask)

#     def _refine_with_model(self, bgr: np.ndarray, coarse: np.ndarray) -> np.ndarray:
#         """
#         Refinement using your trained model.
#         MLWeedDetector.score_mask(bgr, coarse) -> mask 0..255
#         """
#         # Ensure contiguous to avoid negative strides inside the refiner
#         bgr = np.ascontiguousarray(bgr)
#         coarse = np.ascontiguousarray(coarse)

#         refined = self.refiner.score_mask(bgr, coarse)
#         if refined.dtype != np.uint8:
#             refined = np.clip(refined, 0, 255).astype(np.uint8)
#         return refined

#     def _binarize(self, mask: np.ndarray, thresh: int) -> np.ndarray:
#         if mask.dtype != np.uint8:
#             mask = np.clip(mask, 0, 255).astype(np.uint8)
#         _, mask_bin = cv2.threshold(mask, thresh, 255, cv2.THRESH_BINARY)
#         return np.ascontiguousarray(mask_bin)

#     def _remove_small(self, mask_bin: np.ndarray, min_area: int) -> np.ndarray:
#         if min_area <= 1:
#             return mask_bin
#         m01 = (mask_bin > 0).astype(np.uint8)
#         num_labels, labels = cv2.connectedComponents(m01)
#         out = np.zeros_like(m01)
#         for i in range(1, num_labels):  # 0 = background
#             comp = (labels == i)
#             if int(comp.sum()) >= min_area:
#                 out[comp] = 1
#         return (out * 255).astype(np.uint8)

#     def _mask_to_detections(self, mask_bin: np.ndarray) -> List[Detection]:
#         num, labels, stats, _ = cv2.connectedComponentsWithStats(
#             (mask_bin > 0).astype(np.uint8), connectivity=8
#         )
#         dets: List[Detection] = []
#         for i in range(1, num):  # 0 = background
#             x, y, w, h, area = stats[i]
#             if area < self.min_component_area:
#                 continue
#             if (w * h) < self.min_bbox_area:
#                 continue
#             conf = float(min(1.0, area / max(1.0, self.conf_area_norm)))
#             dets.append(
#                 Detection(
#                     x=float(x), y=float(y), w=float(w), h=float(h),
#                     area=float(area), confidence=conf, label="disease"
#                 )
#             )
#         return dets

#     # ---------- Severity & Alert JSON ----------

#     def _severity_from_detections(self, dets: List[Detection]) -> float:
#         """
#         Define severity from detections.
#         Default: max confidence over all detections.
#         You can change this to sum/mean/etc if needed.
#         """
#         return max((d.confidence for d in dets), default=0.0)

#     def _post_alert_json(
#         self,
#         *,
#         severity: float,
#         alert_type: str,
#         image_url: Optional[str],
#         lat: Optional[float],
#         lon: Optional[float],
#         confidence: Optional[float],
#         meta: Optional[Dict[str, Any]],
#     ) -> None:
#         """
#         POST a JSON alert to the configured Alertmanager URL.
#         If your Alertmanager expects a list of alerts, send [payload] instead of payload.
#         """
#         payload: Dict[str, Any] = {
#             # --- Required fields ---
#             "alert_id": str(uuid.uuid4()),
#             "alert_type": alert_type,
#             "device_id": self.device_id,
#             "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
#             # --- Optional / dynamics ---
#             "severity": float(severity),
#         }
#         if confidence is not None:
#             payload["confidence"] = float(confidence)
#         if self.area_name:
#             payload["area"] = self.area_name
#         if lat is not None:
#             payload["lat"] = float(lat)
#         if lon is not None:
#             payload["lon"] = float(lon)
#         if image_url:
#             payload["image_url"] = image_url
#         if meta:
#             payload["meta"] = meta

#         # Some setups require a list of alerts: requests.post(self.alert_url, json=[payload], timeout=5)
#         requests.post(self.alert_url, json=payload, timeout=5)


# # Optional: quick local test (won't run in production compose)
# if __name__ == "__main__":
#     # Minimal smoke test for severity/POST path (won't run inference here).
#     dets = [
#         Detection(x=0, y=0, w=10, h=10, area=4000, confidence=0.2),
#         Detection(x=15, y=15, w=20, h=20, area=9000, confidence=0.6),
#     ]
#     dd = DiseaseDetector()
#     sev = dd._severity_from_detections(dets)
#     print("Severity example:", sev)
#     if sev > dd.alert_thresh:
#         dd._post_alert_json(
#             severity=sev, alert_type="disease_detected",
#             image_url=None, lat=None, lon=None,
#             confidence=sev, meta={"note": "dry run"},
#         )
