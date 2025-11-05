# import cv2, numpy as np, onnxruntime as ort
# from collections import deque
# from typing import List, Tuple
# from .config import CONF, ROI, MIN_OVERLAP, VOTE_N, VOTE_M, VOTE_COOLDOWN, IMG_SIZE, ONNX_PATH

# def letterbox(im, new_shape=640, color=(114,114,114)):
#     h, w = im.shape[:2]
#     r = min(new_shape/h, new_shape/w)
#     nh, nw = int(round(h*r)), int(round(w*r))
#     im_resized = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_LINEAR)
#     canvas = np.full((new_shape, new_shape, 3), color, dtype=np.uint8)
#     canvas[:nh, :nw] = im_resized
#     return canvas

# def overlap_ratio_with_roi(box, H, ymin_frac, ymax_frac):
#     x1,y1,x2,y2 = box
#     box_h = max(0.0, y2 - y1)
#     if box_h <= 0: return 0.0
#     roi_y1 = ymin_frac * H
#     roi_y2 = ymax_frac * H
#     inter_h = max(0.0, min(y2, roi_y2) - max(y1, roi_y1))
#     return inter_h / (box_h + 1e-9)

# def filter_boxes_by_roi(boxes, H, ymin_frac, ymax_frac, min_overlap=0.20):
#     # boxes: ndarray [N,6] = x1,y1,x2,y2,conf,cls
#     keep=[]
#     for b in boxes:
#         if overlap_ratio_with_roi(b[:4], H, ymin_frac, ymax_frac) >= min_overlap:
#             keep.append(b)
#     return np.array(keep) if keep else np.empty((0,6), dtype=np.float32)

# class VoteNM:
#     def __init__(self, N=2, M=3, cooldown_frames=10):
#         self.N=N; self.M=M; self.buf=deque(maxlen=M)
#         self.curr=0; self.cooldown=cooldown_frames
#     def update(self, detected: bool):
#         if self.curr>0: self.curr-=1
#         self.buf.append(1 if detected else 0)
#         if len(self.buf)==self.M and sum(self.buf)>=self.N and self.curr==0:
#             self.curr=self.cooldown
#             return True
#         return False

# class OnnxDetector:
#     def __init__(self, onnx_path=ONNX_PATH, img_size=IMG_SIZE, conf=CONF, roi=ROI, min_overlap=MIN_OVERLAP,
#                  vote_n=VOTE_N, vote_m=VOTE_M, cooldown=VOTE_COOLDOWN):
#         self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
#         self.img_size = img_size
#         self.conf = float(conf)
#         self.voter = VoteNM(vote_n, vote_m, cooldown)
#         self.use_roi=False; self.ymin=self.ymax=0.0
#         if isinstance(roi, str) and roi.lower()!="none":
#             y0,y1 = map(float, roi.split("-"))
#             self.use_roi=True; self.ymin=y0; self.ymax=y1

#         self.input_name = self.session.get_inputs()[0].name
#         self.out_name = self.session.get_outputs()[0].name  # "output0"

#     def infer_image(self, img_bgr):
#         H, W = img_bgr.shape[:2]
#         lb = letterbox(img_bgr, self.img_size)
#         x = lb.transpose(2,0,1)[None].astype(np.float32)/255.0

#         pred = self.session.run([self.out_name], {self.input_name: x})[0]
#         # pred: [N,6] -> x1,y1,x2,y2,conf,cls  (Ultralytics ONNX with NMS)
#         if pred is None or len(pred)==0:
#             det = np.empty((0,6), dtype=np.float32)
#         else:
#             det = pred[pred[:,4] >= self.conf].astype(np.float32)

#         if self.use_roi and len(det)>0:
#             det = filter_boxes_by_roi(det, H, self.ymin, self.ymax, min_overlap=MIN_OVERLAP)

#         detected = len(det)>0
#         fired = self.voter.update(detected)
#         max_conf = float(det[:,4].max()) if detected else 0.0

#         # חוזרים: תיבות (x1,y1,x2,y2,conf,cls), דגל detected, דגל fired, קונפ' מקסימלי
#         return det, detected, fired, max_conf


# services/fence_hole_detector/infer.py
# Notes:
# - Comments are in English only.
# - This version normalizes Ultralytics ONNX outputs to a common (N, 6) tensor:
#   [x1, y1, x2, y2, conf, cls]. It supports common layouts like (1, 5, 8400),
#   (1, 6, 8400), (1, 84, 8400) and the post-NMS format (N, 6).
# - A simple NMS is applied when the raw output is anchor-style (A, C).
# - Boxes are mapped back from the 640x640 letterboxed canvas to original image
#   coordinates so ROI filtering uses the correct image height.

import cv2
import numpy as np
import onnxruntime as ort
from collections import deque
from typing import List, Tuple
from .config import (
    CONF, ROI, MIN_OVERLAP, VOTE_N, VOTE_M, VOTE_COOLDOWN, IMG_SIZE, ONNX_PATH
)

# ----------------------- image utilities ----------------------- #

def letterbox(im: np.ndarray, new_shape: int = 640, color=(114, 114, 114)) -> np.ndarray:
    """
    Resize with unchanged aspect ratio (scale) and pad to a square canvas.
    Padding is placed on the right/bottom only (top-left anchored).
    Returns a (new_shape, new_shape, 3) uint8 image.
    """
    h, w = im.shape[:2]
    r = min(new_shape / h, new_shape / w)
    nh, nw = int(round(h * r)), int(round(w * r))
    im_resized = cv2.resize(im, (nw, nh), interpolation=cv2.INTER_LINEAR)
    canvas = np.full((new_shape, new_shape, 3), color, dtype=np.uint8)
    canvas[:nh, :nw] = im_resized
    return canvas

def xywh_to_xyxy(xywh: np.ndarray) -> np.ndarray:
    """Convert [x, y, w, h] to [x1, y1, x2, y2]."""
    x, y, w, h = np.split(xywh, 4, axis=1)
    x1 = x - w / 2.0
    y1 = y - h / 2.0
    x2 = x + w / 2.0
    y2 = y + h / 2.0
    return np.concatenate([x1, y1, x2, y2], axis=1)

# ----------------------- ONNX output normalization ----------------------- #

def _to_xywh_conf_cls(raw: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Normalize raw ONNX output to (A, 5 or more) and return:
      - xywh_conf: (A, 5) float32 = [x, y, w, h, conf]
      - cls_idx:  (A, 1) float32 = best class id (0 when single-class)
    Supports typical Ultralytics shapes:
      (1, 5, 8400), (1, 6, 8400), (1, 84, 8400), (A, 5/6/84) and post-NMS (N, 6).
    """
    arr = raw

    # If it is already post-NMS of shape (N, 6): [x1,y1,x2,y2,conf,cls] -> convert back to xywh for uniformity
    if arr.ndim == 2 and arr.shape[1] == 6 and (arr.dtype == np.float32 or arr.dtype == np.float64):
        # We will treat it specially in the caller (no further NMS required).
        # Return a marker by sending empty xywh; caller detects via None.
        return None, None  # type: ignore[return-value]

    # Squeeze batch dim if present
    if arr.ndim == 3 and arr.shape[0] == 1:
        arr = np.squeeze(arr, axis=0)  # (C, A)
    elif arr.ndim == 4 and arr.shape[0] == 1:
        arr = np.squeeze(arr, axis=0)

    # If layout is (C, A), transpose to (A, C)
    if arr.ndim == 2 and arr.shape[0] in (5, 6, 84):
        arr = arr.T  # (A, C)

    if arr.ndim != 2:
        raise ValueError(f"Unexpected ONNX output shape {raw.shape}")

    A, C = arr.shape
    arr = arr.astype(np.float32)

    if C == 5:
        # [x,y,w,h,conf] single-class
        xywh_conf = arr[:, :5]
        cls_idx = np.zeros((A, 1), dtype=np.float32)
    elif C == 6:
        # Either [x,y,w,h,obj,cls] for single-class or already has 2 confidences.
        obj = arr[:, 4:5]
        cls_score = arr[:, 5:6]
        conf = obj * cls_score
        xywh_conf = np.concatenate([arr[:, :4], conf], axis=1)
        cls_idx = np.zeros((A, 1), dtype=np.float32)  # single-class
    elif C > 6:
        # [x,y,w,h,obj, cls0..clsN]
        obj = arr[:, 4:5]
        cls_scores = arr[:, 5:]
        cls_idx = np.argmax(cls_scores, axis=1, keepdims=True).astype(np.float32)
        max_cls = np.max(cls_scores, axis=1, keepdims=True)
        conf = obj * max_cls
        xywh_conf = np.concatenate([arr[:, :4], conf], axis=1)
    else:
        raise ValueError(f"Unsupported channel count C={C} in ONNX output")

    return xywh_conf, cls_idx

# ----------------------- NMS utilities ----------------------- #

def _iou_xyxy(box: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """Compute IoU between one box [x1,y1,x2,y2] and many boxes."""
    x1 = np.maximum(box[0], boxes[:, 0])
    y1 = np.maximum(box[1], boxes[:, 1])
    x2 = np.minimum(box[2], boxes[:, 2])
    y2 = np.minimum(box[3], boxes[:, 3])

    inter = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    area1 = (box[2] - box[0]) * (box[3] - box[1])
    area2 = (boxes[:, 2] - boxes[:, 0]) * (boxes[:, 3] - boxes[:, 1])
    union = np.maximum(area1 + area2 - inter, 1e-9)
    return inter / union

def nms_xyxy(boxes: np.ndarray, scores: np.ndarray, iou_th: float = 0.45, topk: int = 300) -> List[int]:
    """
    Greedy NMS. boxes: (N,4) in xyxy, scores: (N,)
    Returns list of kept indices.
    """
    idxs = scores.argsort()[::-1]
    keep: List[int] = []
    while idxs.size > 0:
        i = int(idxs[0])
        keep.append(i)
        if len(keep) >= topk or idxs.size == 1:
            break
        ious = _iou_xyxy(boxes[i], boxes[idxs[1:]])
        idxs = idxs[1:][ious < iou_th]
    return keep

# ----------------------- ROI helpers ----------------------- #

def overlap_ratio_with_roi(box: np.ndarray, H: int, ymin_frac: float, ymax_frac: float) -> float:
    x1, y1, x2, y2 = box
    box_h = max(0.0, y2 - y1)
    if box_h <= 0:
        return 0.0
    roi_y1 = ymin_frac * H
    roi_y2 = ymax_frac * H
    inter_h = max(0.0, min(y2, roi_y2) - max(y1, roi_y1))
    return inter_h / (box_h + 1e-9)

def filter_boxes_by_roi(boxes: np.ndarray, H: int, ymin_frac: float, ymax_frac: float,
                        min_overlap: float = 0.20) -> np.ndarray:
    # boxes: ndarray [N,6] = x1,y1,x2,y2,conf,cls
    keep = []
    for b in boxes:
        if overlap_ratio_with_roi(b[:4], H, ymin_frac, ymax_frac) >= min_overlap:
            keep.append(b)
    return np.array(keep, dtype=np.float32) if keep else np.empty((0, 6), dtype=np.float32)

# ----------------------- vote logic ----------------------- #

class VoteNM:
    def __init__(self, N=2, M=3, cooldown_frames=10):
        self.N = N
        self.M = M
        self.buf = deque(maxlen=M)
        self.curr = 0
        self.cooldown = cooldown_frames

    def update(self, detected: bool) -> bool:
        if self.curr > 0:
            self.curr -= 1
        self.buf.append(1 if detected else 0)
        if len(self.buf) == self.M and sum(self.buf) >= self.N and self.curr == 0:
            self.curr = self.cooldown
            return True
        return False

# ----------------------- detector ----------------------- #

class OnnxDetector:
    def __init__(
        self,
        onnx_path=ONNX_PATH,
        img_size=IMG_SIZE,
        conf=CONF,
        roi=ROI,
        min_overlap=MIN_OVERLAP,
        vote_n=VOTE_N,
        vote_m=VOTE_M,
        cooldown=VOTE_COOLDOWN,
    ):
        self.session = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        self.img_size = int(img_size)
        self.conf = float(conf)
        self.voter = VoteNM(vote_n, vote_m, cooldown)
        self.use_roi = False
        self.ymin = self.ymax = 0.0
        if isinstance(roi, str) and roi.lower() != "none":
            y0, y1 = map(float, roi.split("-"))
            self.use_roi = True
            self.ymin = y0
            self.ymax = y1

        self.input_name = self.session.get_inputs()[0].name
        self.out_name = self.session.get_outputs()[0].name  # usually "output0"

    def infer_image(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, bool, bool, float]:
        H, W = img_bgr.shape[:2]
        canvas = letterbox(img_bgr, self.img_size)

        # Build input blob (NCHW, normalized to [0,1])
        x = canvas.transpose(2, 0, 1)[None].astype(np.float32) / 255.0

        # ONNX forward
        raw = self.session.run([self.out_name], {self.input_name: x})[0]

        # Detect whether output is already post-NMS (N,6). If yes, use it directly.
        det: np.ndarray
        if raw.ndim == 2 and raw.shape[1] == 6:
            det = raw.astype(np.float32)
            # det currently in canvas coordinates; we will rescale below.
        else:
            # Normalize to (A,5) and best class id
            xywh_conf, cls_idx = _to_xywh_conf_cls(raw)
            # Confidence filter
            mask = xywh_conf[:, 4] >= self.conf
            xywh_conf = xywh_conf[mask]
            cls_idx = cls_idx[mask]
            if xywh_conf.size == 0:
                det = np.empty((0, 6), dtype=np.float32)
            else:
                # Convert to xyxy
                xyxy = xywh_to_xyxy(xywh_conf[:, :4])
                scores = xywh_conf[:, 4]

                # NMS
                keep = nms_xyxy(xyxy, scores, iou_th=0.45, topk=300)
                xyxy = xyxy[keep]
                scores = scores[keep]
                cls_idx = cls_idx[keep]

                det = np.concatenate(
                    [xyxy.astype(np.float32),
                     scores.reshape(-1, 1).astype(np.float32),
                     cls_idx.astype(np.float32)],
                    axis=1
                )  # (N, 6)

        # Map boxes from canvas (img_size) back to original (H, W)
        if det.size > 0:
            r = min(self.img_size / H, self.img_size / W)  # same ratio used in letterbox()
            det[:, [0, 2]] = det[:, [0, 2]] / r
            det[:, [1, 3]] = det[:, [1, 3]] / r
            # Clip to image bounds
            det[:, 0::2] = np.clip(det[:, 0::2], 0, W - 1e-3)
            det[:, 1::2] = np.clip(det[:, 1::2], 0, H - 1e-3)

        # Optional ROI filtering on original image scale
        if self.use_roi and det.size > 0:
            det = filter_boxes_by_roi(det, H, self.ymin, self.ymax, min_overlap=MIN_OVERLAP)

        detected = det.size > 0
        fired = self.voter.update(detected)
        max_conf = float(det[:, 4].max()) if detected else 0.0

        # Return: boxes [x1,y1,x2,y2,conf,cls], detected flag, fired flag, max confidence
        return det.astype(np.float32), detected, fired, max_conf
