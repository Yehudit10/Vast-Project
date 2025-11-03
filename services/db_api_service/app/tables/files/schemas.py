# app/tables/files/schemas.py
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field, NonNegativeInt


class FilesCreate(BaseModel):
    bucket: str
    object_key: str = Field(alias="object_key")
    content_type: Optional[str] = None
    size_bytes: Optional[NonNegativeInt] = None
    etag: Optional[str] = None
    mission_id: Optional[int] = None
    device_id: Optional[str] = None
    tile_id: Optional[str] = None
    footprint: Optional[str] = None   # WKT
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True


class FilesUpdate(BaseModel):
    content_type: Optional[str] = None
    size_bytes: Optional[NonNegativeInt] = None
    etag: Optional[str] = None
    mission_id: Optional[int] = None
    device_id: Optional[str] = None
    tile_id: Optional[str] = None
    footprint: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
