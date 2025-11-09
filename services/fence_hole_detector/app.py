# services/fence_hole_detector/app.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
import os, io, cv2, numpy as np
from minio import Minio
from datetime import datetime, timezone
from dotenv import load_dotenv

from .infer import OnnxDetector
from .alert_client import post_alert  # used only if alerts are enabled

# Load .env next to this file if present
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# --- Config (env-first) ---
ONNX_PATH = os.getenv("FENCE_ONNX_PATH", "best.onnx")
CONF = float(os.getenv("FENCE_CONF", "0.35"))

MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET     = os.getenv("MINIO_BUCKET", "rover-images")
MINIO_SECURE     = os.getenv("MINIO_SECURE", "false").lower() == "true"
PUBLIC_BASE_URL  = os.getenv("MINIO_PUBLIC_BASE_URL", "").rstrip("/")

DEFAULT_DEVICE_ID = os.getenv("DEFAULT_DEVICE_ID", "camera-01")
DEFAULT_AREA      = os.getenv("DEFAULT_AREA", "north_field")
DEFAULT_SEVERITY  = int(os.getenv("DEFAULT_SEVERITY", "3"))

# Critical: alerts flag (0/1). When 0, service will never talk to Kafka.
ALERT_ENABLED = os.getenv("ALERT_ENABLED", "0") == "1"

# --- App objects ---
app = FastAPI(title="fence_hole_detector")

detector = OnnxDetector(
    onnx_path=ONNX_PATH,
    conf=CONF,
    roi=os.getenv("FENCE_ROI", "none"),
    vote_n=int(os.getenv("FENCE_VOTE_N", "1")),
    vote_m=int(os.getenv("FENCE_VOTE_M", "1")),
    cooldown=int(os.getenv("FENCE_VOTE_COOLDOWN", "0")),
)

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=MINIO_SECURE,
)

# --- Schemas ---
class ProcessReq(BaseModel):
    bucket: str = Field(default_factory=lambda: MINIO_BUCKET)
    key: str
    captured_at: Optional[datetime] = None  # ISO, e.g. "2025-10-29T14:32:12Z"
    device_id: Optional[str] = None
    area: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None

class ProcessResp(BaseModel):
    detected_boxes: int
    fired_alert: int
    max_conf: float
    alert_id: Optional[str] = None
    image_url: Optional[str] = None

# --- Helpers ---
def read_minio_image(bucket: str, key: str):
    try:
        resp = minio_client.get_object(bucket, key)
        data = resp.read()
        resp.close(); resp.release_conn()
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"MinIO get_object failed: {e}")
    img_array = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=415, detail="Failed to decode image")
    return img

def build_image_url(bucket: str, key: str) -> str:
    # Prefer a public base URL if provided, else use presigned URL for 24h
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL}/{key}"
    try:
        return minio_client.get_presigned_url("GET", bucket, key, expires=24*60*60)
    except Exception:
        scheme = "https" if MINIO_SECURE else "http"
        return f"{scheme}://{MINIO_ENDPOINT}/{bucket}/{key}"

# --- Health ---
@app.get("/health")
def health():
    return {"status": "ok"}

# --- Main endpoint: Flink -> HTTP ---
@app.post("/process_minio", response_model=ProcessResp)
def process_minio(req: ProcessReq):
    bucket = req.bucket or MINIO_BUCKET
    key = req.key
    if not key:
        raise HTTPException(400, "key is required")

    # 1) Read image from MinIO
    img = read_minio_image(bucket, key)

    # 2) Inference
    det, detected, fired, max_conf = detector.infer_image(img)

    # 3) Optional alert
    alert_id = None
    image_url = build_image_url(bucket, key) if detected else None

    if detected and ALERT_ENABLED:
        try:
            started_at = req.captured_at or datetime.now(timezone.utc)
            alert_id = post_alert(
                device_id=req.device_id or DEFAULT_DEVICE_ID,
                started_at=started_at,
                confidence=max_conf,
                image_url=image_url,
                area=req.area or DEFAULT_AREA,
                lat=req.lat, lon=req.lon,
                severity=DEFAULT_SEVERITY,
                extra={"bucket": bucket, "key": key},
            )
        except Exception as e:
            # Never fail the request because of the alert pipeline
            # (log prints will appear in the Uvicorn console)
            print(f"[WARN] alert send failed: {e}")

    # Note: fired_alert == 1 means "detected now" (no voting when camera batches)
    return ProcessResp(
        detected_boxes=int(len(det)),
        fired_alert=int(1 if detected else 0),
        max_conf=float(max_conf),
        alert_id=alert_id,
        image_url=image_url,
    )
