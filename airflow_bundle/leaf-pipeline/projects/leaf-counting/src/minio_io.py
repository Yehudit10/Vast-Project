from __future__ import annotations
import io, json, os
from pathlib import Path
import cv2
from minio import Minio
from minio.error import S3Error

def get_client(endpoint: str, access_key: str, secret_key: str, secure: bool=False) -> Minio:
    """
    דוגמה:
      cli = get_client("localhost:9000", "minioadmin", "minioadmin", secure=False)
    """
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)

def ensure_bucket(cli: Minio, bucket: str):
    found = cli.bucket_exists(bucket)
    if not found:
        cli.make_bucket(bucket)

def put_png(cli: Minio, bucket: str, key: str, img_bgr):
    """
    מעלה תמונת PNG מתוך np.ndarray (BGR של OpenCV).
    """
    Path(key).parent and os.makedirs(Path(key).parent, exist_ok=True)  # לא חובה, לשקט נפשי מקומי
    ok, buf = cv2.imencode(".png", img_bgr)
    if not ok:
        raise RuntimeError("cv2.imencode PNG failed")
    bio = io.BytesIO(buf.tobytes())
    bio.seek(0)
    cli.put_object(bucket, key, bio, length=len(bio.getvalue()), content_type="image/png")

def put_json(cli: Minio, bucket: str, key: str, obj):
    """
    מעלה JSON (dict/list).
    """
    js = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    bio = io.BytesIO(js)
    bio.seek(0)
    cli.put_object(bucket, key, bio, length=len(js), content_type="application/json")
