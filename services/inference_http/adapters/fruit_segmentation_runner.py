import os, tempfile, hashlib, cv2, numpy as np, boto3, torch, json
import re
from datetime import datetime
from kafka import KafkaProducer
import psycopg2

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
from datetime import datetime
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
        self.producer = KafkaProducer(
            bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"),
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        self.output_topic = "flink-dispatcher-fruit"
        self.db = psycopg2.connect(
            host=os.getenv("PGHOST", "postgres"),
            port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "missions_db"),
            user=os.getenv("PGUSER", "missions_user"),
            password=os.getenv("PGPASSWORD", "pg123")
        )
        self.db.autocommit = True



    def publish_event(self, data: dict):
        """Publish fruit metadata to Kafka topic."""
        try:
            self.producer.send(self.output_topic, data)
            self.producer.flush()
        except Exception as e:
            print(f"[ERROR] failed to publish event: {e}", flush=True)

    def write_fruit_record(
        self,
        original_key,
        cropped_key,
        bucket,
        device_id,
        timestamp_str,
        x1, y1, x2, y2,
        label,
        latency
    ):
        cur = self.db.cursor()
        cur.execute(
            """
            INSERT INTO fruit_detections (
                original_key,
                cropped_key,
                bucket,
                device_id,
                timestamp,
                x1, y1, x2, y2,
                label,
                latency_ms_model
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
            """,
            (
                original_key,
                cropped_key,
                bucket,
                device_id,
                timestamp_str,
                x1, y1, x2, y2,
                label,
                latency
            )
        )
        cur.close()


    def run(self, image_bytes: bytes | None = None, model_tag=None, extra=None) -> Dict[str, Any]:
        """Main inference entrypoint for HTTP"""
        bucket_in = extra.get("bucket") if extra else "imagery"
        key = extra.get("key") if extra else None
        if not key:
            return {"error": "missing key"}
    

        if image_bytes:
            img_array = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if img is None:
                return {"error": "failed to decode image from bytes"}
        else:
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
            with tempfile.TemporaryDirectory() as tmpdir:
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
                    
                    base_name = os.path.splitext(os.path.basename(key))[0]
                    match = re.match(r"([a-zA-Z0-9-]+)_(\d{8}T\d{6}Z)", base_name)
                    if match:
                        device_id, timestamp_str = match.groups()
                        timestamp = datetime.strptime(timestamp_str, "%Y%m%dT%H%M%SZ")
                        date_part = timestamp.strftime("%Y-%m-%d")
                    else:
                        device_id = "unknown_device"
                        date_part = "unknown_date"
                    count += 1
                    out_name = f"{base_name}.jpg"
                    out_key = f"fruit/fruits/{device_id}/{date_part}/{out_name}"
                    out_path = os.path.join(tmpdir, out_name)
                    cv2.imwrite(out_path, crop)
                    
                    self.s3.upload_file(out_path, bucket_in, out_key)
                    
                    event = {
                        "ok": True,
                        "team": "camera",
                        "bucket": bucket_in,
                        "key": out_key,
                        "label": "fruit",
                        "device_id": device_id,
                        "timestamp": timestamp_str,
                        "latency_ms_model": latency_ms,
                        "original_key": key,
                        "bbox": {
                            "x1": int(x1),
                            "y1": int(y1),
                            "x2": int(x2),
                            "y2": int(y2)
                        }
                    }
                    self.publish_event(event)
                    self.write_fruit_record(
                        original_key=key,      
                        cropped_key=out_key,       
                        bucket=bucket_in,
                        device_id=device_id,
                        timestamp_str=timestamp_str,
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        label="fruit",
                        latency=latency_ms
                    )

    pass