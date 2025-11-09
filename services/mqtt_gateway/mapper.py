# services/mqtt_gateway/mapper.py
# Purpose: pure functions to compute MinIO object key & Kafka event from MQTT topic parts.
# No network. Easy to unit-test.

from __future__ import annotations
from datetime import datetime, timezone
from typing import Tuple, Optional
from uuid import uuid4
import os

from .models import MinioObject, ImageInfo, KafkaEvent


def safe_ext(filename: str, default: str = ".jpg") -> str:
    """Return a safe file extension with dot. Fallback to default if missing/invalid."""
    _, ext = os.path.splitext(filename)
    ext = (ext or "").strip().lower()
    if not ext or len(ext) > 8 or any(c in ext for c in " \t/\\"):
        return default
    return ext


def date_parts_from_epoch_ms(ts_ms: int) -> Tuple[str, str, str]:
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    return f"{dt.year:04d}", f"{dt.month:02d}", f"{dt.day:02d}"


# def build_minio_key(sensor_id: str, ts_ms: int, filename: str) -> str:
#     """images/{sensor}/{YYYY}/{MM}/{DD}/{sensor}_{ts}{ext}"""
#     y, m, d = date_parts_from_epoch_ms(ts_ms)
#     ext = safe_ext(filename)
#     base = f"{sensor_id}_{ts_ms}{ext}"
#     return f"images/{sensor_id}/{y}/{m}/{d}/{base}"

def build_minio_key(
    sensor_id: str,
    ts_ms: int,
    filename: str,
    *,
    incident_id: str,
    rover_type: str = "rover-car",
    prefix: str = "security/incidents",
) -> str:
    """
    Build canonical S3 key:
      imagery/security/incidents/<rover_type>/<incident_id>/<sensor_id>_<ts_ms><ext>

    Notes:
    - `incident_id` must be provided by the caller (stable folder per incident).
    - `rover_type` has a sensible default ("rover-car") but can be overridden.
    """
    ext = safe_ext(filename, default=".jpg")
    base = f"{sensor_id}_{ts_ms}{ext}"
    return f"{prefix}/{rover_type}/{incident_id}/{base}"


def map_to_objects(
    bucket: str,
    info: ImageInfo,
    *,
    sha256: Optional[str] = None,
    size_bytes: Optional[int] = None,
    event_id: Optional[str] = None,
    telemetry: Optional[dict] = None
) -> Tuple[MinioObject, KafkaEvent]:
    """
    Given input image info → compute MinIO object + Kafka event.
    Pure function: no IO. Easy to unit test.
    """
    key = build_minio_key(info.sensor_id, info.captured_ts, info.filename, incident_id=event_id or str(uuid4()))
    mobj = MinioObject(
        bucket=bucket,
        key=key,
        content_type=info.content_type,
        size_bytes=size_bytes,
        sha256=sha256,
    )
    kev = KafkaEvent(
        version=1,
        event_id=(event_id or str(uuid4())),
        sensor_id=info.sensor_id,
        captured_ts=info.captured_ts,
        image=mobj,
        # telemetry=None,
        telemetry=telemetry,
    )
    return mobj, kev
