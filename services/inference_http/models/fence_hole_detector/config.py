import os

# --- Model / Inference ---
ONNX_PATH = os.getenv("FENCE_ONNX_PATH", "runs_fence/y8n_cpu_v1/weights/best.onnx")
CONF = float(os.getenv("FENCE_CONF", "0.35"))

# ROI: "none" or "ymin-ymax" ("0.20-0.85")
ROI = os.getenv("FENCE_ROI", "none")
MIN_OVERLAP = float(os.getenv("FENCE_MIN_OVERLAP", "0.20"))

VOTE_N = int(os.getenv("FENCE_VOTE_N", "1"))
VOTE_M = int(os.getenv("FENCE_VOTE_M", "1"))
VOTE_COOLDOWN = int(os.getenv("FENCE_VOTE_COOLDOWN", "0")) 

IMG_SIZE = int(os.getenv("FENCE_IMG_SIZE", "640"))

# --- MinIO ---
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_BUCKET     = os.getenv("MINIO_BUCKET", "")
MINIO_SECURE     = os.getenv("MINIO_SECURE", "false").lower() == "true"

# --- Alert Manager ---
ALERT_MANAGER_URL = os.getenv("ALERT_MANAGER_URL", "")  #  http://localhost:9093/api/v2/alerts
ALERT_ENABLE_AUTO_POST = os.getenv("ALERT_ENABLE_AUTO_POST", "false").lower() == "true"
