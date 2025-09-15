# services/rover_ingest/storage_minio.py
import os
from pathlib import PurePosixPath  # <-- MUST be imported at top
from minio import Minio

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS   = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET   = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET   = os.getenv("MINIO_BUCKET", "rover-images")

_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS,
    secret_key=MINIO_SECRET,
    secure=False,  # set True only if TLS is enabled
)

def _normalize_key(s3_key: str) -> str:
    """
    Accept both forms:
    1) 'rover-07/2025/09/10/xxx.jpg'  (preferred)
    2) 'rover-images/rover-07/...'
    This removes a leading bucket prefix if present and normalizes slashes.
    """
    key = s3_key.replace("\\", "/").lstrip("/")
    bucket_prefix = f"{MINIO_BUCKET}/"
    if key.startswith(bucket_prefix):
        key = key[len(bucket_prefix):]
    return str(PurePosixPath(key))

def object_exists(s3_key: str) -> bool:
    key = _normalize_key(s3_key)
    try:
        _client.stat_object(MINIO_BUCKET, key)
        return True
    except Exception:
        return False
