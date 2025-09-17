from datetime import datetime, timezone, timedelta
from .schema import ImageMeta
# from .storage_minio import object_exists
from . import storage_minio


MAX_CLOCK_SKEW = timedelta(minutes=5)
FUTURE_DRIFT   = timedelta(seconds=5)

def validate_semantics(meta: ImageMeta) -> None:
    # Time rules
    now = datetime.now(timezone.utc)
    source_ts = getattr(meta, "source_ts", None)
    captured_at = getattr(meta, "captured_at", None)

    if source_ts and source_ts > now + FUTURE_DRIFT:
        raise ValueError("source_ts in the future")
    if captured_at and captured_at > now + FUTURE_DRIFT:
        raise ValueError("captured_at in the future")
    if source_ts and abs(meta.captured_at - source_ts) > MAX_CLOCK_SKEW:
        # you may raise or just log; here we only warn by comment
        pass

    # GPS range
    if not (-90.0 <= meta.gps.lat <= 90.0):
        raise ValueError("lat out of range")
    if not (-180.0 <= meta.gps.lon <= 180.0):
        raise ValueError("lon out of range")

    # S3 existence (MinIO)
    if not storage_minio.object_exists(meta.s3_key):
        raise FileNotFoundError(f"s3_key not found: {meta.s3_key}")
    # if not object_exists(meta.s3_key):
    #     raise FileNotFoundError(f"s3_key not found: {meta.s3_key}")
