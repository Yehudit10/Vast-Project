from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, validator

class GPS(BaseModel):
    lat: float
    lon: float
    gps_accuracy_m: Optional[float] = None

class ImageMeta(BaseModel):
    # Required
    schema_ver: int = 1
    device_id: str
    image_id: str
    captured_at: datetime
    gps: GPS
    heading_deg: Optional[float] = None
    alt_m: Optional[float] = None
    s3_key: str
    meta_src: Literal["manifest", "telemetry", "exif_fallback"]

    # Recommended
    pitch_deg: Optional[float] = 0.0
    roll_deg: Optional[float] = 0.0
    fov_deg: Optional[float] = None
    temp_c: Optional[float] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    sha256: Optional[str] = None
    exif_present: Optional[bool] = None
    firmware: Optional[str] = None
    capture_seq: Optional[int] = None
    signature: Optional[str] = None
    trace_id: Optional[str] = None
    source_ts: Optional[datetime] = None

    @validator("heading_deg", pre=True, always=True)
    def normalize_heading(cls, v):
        if v is None:
            return v
        return float(v) % 360.0  # keep in [0,360)

    @validator("captured_at")
    def require_datetime(cls, v: datetime):
        # Expect ISO8601 from producer; if tz is missing, treat as UTC upstream.
        return v
