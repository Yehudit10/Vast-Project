import os, io, tempfile, hashlib, cv2, numpy as np, boto3, torch

def allow_unrestricted_torch_load():
    _original_load = torch.load
    def patched_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return _original_load(*args, **kwargs)
    torch.load = patched_load

allow_unrestricted_torch_load()
# === End Patch ===

import time
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from ultralytics import YOLO

def sha256_hex(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

class FruitSegmentationRunner:
    def __init__(self, weights_path: Optional[str] = None, model_tag: Optional[str] = None):
        self.weights_path = weights_path or os.getenv("WEIGHTS_PATH", "/app/weights/yolov8-fruits.pt")
        self.model = YOLO(self.weights_path)
        raw_endpoint = os.getenv("MINIO_ENDPOINT", "minio-hot:9000").strip()
        if not raw_endpoint.startswith(("http://", "https://")):
            endpoint = f"http://{raw_endpoint}"
        else:
            endpoint = raw_endpoint
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin123")
        )

    def run(self, image_bytes: bytes, model_tag=None, extra=None) -> Dict[str, Any]:
        """Main inference entrypoint for HTTP"""
        bucket_in = extra.get("bucket") if extra else "imagery-hot"
        key = extra.get("key") if extra else None
        if not key:
            return {"error": "missing key"}

        with tempfile.TemporaryDirectory() as tmpdir:
            local_path = os.path.join(tmpdir, os.path.basename(key))
            self.s3.download_file(bucket_in, key, local_path)
            img = cv2.imread(local_path)
            if img is None:
                return {"error": "failed to read image"}

            t0 = time.time()
            results = self.model.predict(img, conf=0.3, iou=0.45, verbose=False)
            latency_ms = int((time.time() - t0) * 1000)
            boxes = results[0].boxes
            count = 0
            if boxes:
                for i, box in enumerate(boxes):
                    label = results[0].names[int(box.cls[0])]
                    if label.lower() not in [
                        "apple", "banana", "orange", "pear", "peach", "plum",
                        "mango", "grape", "cherry", "pomegranate"
                    ]:
                        continue
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    crop = img[y1:y2, x1:x2]
                    if crop.size == 0:
                        continue
                    out_name = f"{os.path.splitext(os.path.basename(key))[0]}_fruit_{i+1}.jpg"
                    out_key = f"segments/{out_name}"
                    out_path = os.path.join(tmpdir, out_name)
                    cv2.imwrite(out_path, crop)
                    self.s3.upload_file(out_path, bucket_in, out_key)
                    count += 1

            return {
                "label": "fruit",
                "count": count,
                "latency_ms_model": latency_ms,
            }
