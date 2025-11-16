# services/inference_http/models/fence_hole_detector/service.py
# Purpose: pure-Python service entrypoints used by both the model's local FastAPI
# and the unified inference_http adapter. No web-specific code here.

from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any
import numpy as np
import cv2
from minio import Minio
from datetime import datetime, timezone
from dotenv import load_dotenv

from .infer import OnnxDetector  # reuses the existing ONNX runtime code
from .alert_client import post_alert

# Load .env next to this file so ALERT_ENABLED / KAFKA_BOOTSTRAP etc. are set.
BASE_DIR = os.path.dirname(__file__)
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ---- Config (env-first) -----------------------------------------------------
# We keep model path under models/<...>/weights/best.onnx inside the image.
DEFAULT_ONNX = "/app/models/fence_hole_detector/weights/best.onnx"
FENCE_ONNX_PATH = os.getenv("FENCE_ONNX_PATH", DEFAULT_ONNX)
FENCE_CONF = float(os.getenv("FENCE_CONF", "0.30"))
FENCE_ROI = os.getenv("FENCE_ROI", "none")
FENCE_VOTE_N = int(os.getenv("FENCE_VOTE_N", "1"))
FENCE_VOTE_M = int(os.getenv("FENCE_VOTE_M", "1"))
FENCE_VOTE_COOLDOWN = int(os.getenv("FENCE_VOTE_COOLDOWN", "0"))

MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "minio-hot:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin123")
MINIO_SECURE     = os.getenv("MINIO_SECURE", "0") == "1"

# Public base URL for building image_url in alerts
MINIO_PUBLIC_BASE_URL = os.getenv(
    "MINIO_PUBLIC_BASE_URL", f"http://{MINIO_ENDPOINT}"
).rstrip("/")

DEFAULT_DEVICE_ID = os.getenv("DEFAULT_DEVICE_ID", "camera-01")
DEFAULT_AREA      = os.getenv("DEFAULT_AREA", "north_field")
DEFAULT_SEVERITY  = int(os.getenv("DEFAULT_SEVERITY", "3"))
# Flag: enable/disable Kafka alerts
ALERT_ENABLED = os.getenv("ALERT_ENABLED", "0") == "1"

# ---- Singletons --------------------------------------------------------------
_detector = OnnxDetector(
    onnx_path=FENCE_ONNX_PATH,
    conf=FENCE_CONF,
    roi=FENCE_ROI,
    vote_n=FENCE_VOTE_N,
    vote_m=FENCE_VOTE_M,
    cooldown=FENCE_VOTE_COOLDOWN,
)

_minio = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)

# ---- Types -------------------------------------------------------------------
@dataclass
class InferenceInput:
    bucket: str
    key: str
    captured_at: Optional[datetime] = None
    device_id: Optional[str] = None
    area: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

def _read_minio_image(bucket: str, key: str) -> np.ndarray:
    """Download object from MinIO and decode as BGR image."""
    resp = _minio.get_object(bucket, key)
    data = resp.read()
    resp.close(); resp.release_conn()
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Failed to decode image from MinIO")
    return img

# ---- Main entrypoint used by adapter ----------------------------------------
def infer_from_minio(inp: InferenceInput) -> Dict[str, Any]:
    """
    Perform inference from a MinIO key and return a normalized dict.

    This function is used by the unified inference_http adapter.
    It may also optionally send a Kafka alert when a hole is detected.
    """
    # 1) Load image from MinIO
    img = _read_minio_image(inp.bucket, inp.key)

    # 2) Run model inference
    det, detected, fired, max_conf = _detector.infer_image(img)

    # 3) Build base result for HTTP / Flink
    result: Dict[str, Any] = {
        "detected_boxes": int(len(det)),
        "fired_alert": int(1 if detected else 0),
        "max_conf": float(max_conf),
        "device_id": inp.device_id or DEFAULT_DEVICE_ID,
        "area": inp.area or DEFAULT_AREA,
        "bucket": inp.bucket,
        "key": inp.key,
        "captured_at": (
            inp.captured_at or datetime.now(timezone.utc)
        ).isoformat().replace("+00:00", "Z"),
    }

    # 4) Optionally send Kafka alert (same behavior as old FastAPI service)
    if detected and ALERT_ENABLED:
        try:
            image_url = f"{MINIO_PUBLIC_BASE_URL}/{inp.bucket}/{inp.key}"
            alert_id = post_alert(
                device_id=result["device_id"],
                started_at=inp.captured_at or datetime.now(timezone.utc),
                confidence=max_conf,
                image_url=image_url,
                area=result["area"],
                lat=inp.lat,
                lon=inp.lon,
                severity=DEFAULT_SEVERITY,
                extra={"bucket": inp.bucket, "key": inp.key},
            )
            result["alert_id"] = alert_id
            result["image_url"] = image_url
        except Exception as exc:
            # Never fail inference because of alert pipeline
            print(f"[WARN] alert send failed: {exc}", flush=True)

    return result