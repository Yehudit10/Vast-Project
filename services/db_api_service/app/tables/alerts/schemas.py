from __future__ import annotations
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class Alert(BaseModel):
    alert_id: int
    alert_type: Optional[str] = None
    device_id: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    confidence: Optional[float] = None
    area: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    severity: Optional[str] = None
    image_url: Optional[str] = None
    vod: Optional[str] = None
    hls: Optional[str] = None
    ack: Optional[bool] = None
    meta: Optional[dict] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AlertImage(BaseModel):
    inference_log_id: int
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None
