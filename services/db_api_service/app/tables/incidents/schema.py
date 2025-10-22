from typing import Optional, Any, Dict, List
from datetime import datetime
from pydantic import BaseModel, Field, NonNegativeInt, conint
from uuid import UUID

# ---------- Incidents ----------

class IncidentBase(BaseModel):
    mission_id: Optional[int] = None
    device_id: Optional[str] = None
    anomaly: Optional[str] = None

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_sec: Optional[float] = None
    frame_start: Optional[NonNegativeInt] = None
    frame_end: Optional[NonNegativeInt] = None

    severity: Optional[float] = None
    is_real: Optional[bool] = None
    ack: Optional[bool] = None  # ✅ NEW: farmer acknowledged or not

    roi_pixels: Optional[Dict[str, Any]] = None
    footprint: Optional[str] = None
    clip_file_id: Optional[int] = None
    poster_file_id: Optional[int] = None
    frames_manifest: Optional[List[Dict[str, Any]]] = None
    meta: Optional[Dict[str, Any]] = None

class IncidentCreate(IncidentBase):
    incident_id: UUID = Field(..., description="UUID")

class IncidentUpsert(IncidentCreate):
    pass

class IncidentUpdate(IncidentBase):
    pass

class IncidentRow(BaseModel):
    incident_id: UUID
    device_id: Optional[str] = None
    mission_id: Optional[int] = None
    anomaly: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_sec: Optional[float] = None
    severity: Optional[float] = None
    is_real: Optional[bool] = None
    ack: Optional[bool] = None  # ✅ NEW
    clip_file_id: Optional[int] = None
    poster_file_id: Optional[int] = None

# ---------- Frames ----------

Detection = Dict[str, Any]

class FrameCreate(BaseModel):
    frame_idx: conint(ge=0)
    ts: datetime
    detections: List[Detection] = []
    cls_name: Optional[str] = None
    cls_id: Optional[str] = None
    file_id: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None

class FramesBulk(BaseModel):
    frames: List[FrameCreate]

class FrameRow(BaseModel):
    frame_idx: int
    ts: datetime
    detections: List[Detection] = []
    cls_name: Optional[str] = None
    cls_id: Optional[str] = None
    file_id: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None
