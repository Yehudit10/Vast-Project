from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Iterable, Optional

from sqlalchemy import text
from agri_baseline.src.pipeline.db import get_engine, INSERT_FINDING, INSERT_QA


@dataclass
class Finding:
    scope: str
    image_id: str
    rule: str
    severity: str
    message: str
    details: Optional[dict] = None


# ---- Image-level checks ----

def check_bbox_bounds(image_id: str, width: int, height: int, dets: list[dict]) -> list[Finding]:
    out: list[Finding] = []
    for d in dets:
        x, y, w, h = d["bbox_x"], d["bbox_y"], d["bbox_w"], d["bbox_h"]
        if x < 0 or y < 0 or x + w > width or y + h > height:
            out.append(Finding("image", image_id, "bbox_oob", "warn",
                               f"BBox out-of-bounds: {(x, y, w, h)}"))
        if w * h <= 0 or d["area_px"] <= 0:
            out.append(Finding("image", image_id, "bbox_area_zero", "error",
                               "Non-positive area"))
        if d["confidence"] < 0 or d["confidence"] > 1:
            out.append(Finding("image", image_id, "conf_oob", "error",
                               f"Confidence out of range: {d['confidence']:.3f}"))
    return out


def check_counts_reasonable(image_id: str, disease: int) -> list[Finding]:
    out: list[Finding] = []
    if disease < 0:
        out.append(Finding("image", image_id, "negative_counts", "error",
                           f"Negative count: disease={disease}"))
    if disease == 0:
        out.append(Finding("image", image_id, "all_zero_counts", "warn",
                           "Disease count is zero"))
    if disease > 10000:
        out.append(Finding("image", image_id, "count_too_high", "warn",
                           f"Suspiciously high disease count: {disease}"))
    return out


# ---- Batch-level checks ----

def check_batch_error_rate(total: int, errored: int, threshold: float = 0.05) -> list[Finding]:
    rate = 0.0 if total == 0 else errored / total
    sev = "warn" if rate <= threshold else "error"
    return [Finding("batch", None, "error_rate", sev,
                    f"Batch error rate={rate:.3%}, threshold={threshold:.0%}")]


def check_batch_no_detections(total: int, sum_dets: int) -> list[Finding]:
    if total > 0 and sum_dets == 0:
        return [Finding("batch", None, "no_detections", "warn",
                        "Pipeline produced zero detections for the entire batch")]
    return []
