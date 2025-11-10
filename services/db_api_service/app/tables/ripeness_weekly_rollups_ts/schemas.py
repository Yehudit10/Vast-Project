from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, conint, confloat


class RipenessWeeklyRollupBase(BaseModel):
    """Base schema for weekly ripeness rollups table."""
    ts: Optional[datetime] = Field(None, description="Insertion timestamp")
    window_start: datetime = Field(..., description="Start of weekly window")
    window_end: datetime = Field(..., description="End of weekly window")
    fruit_type: str = Field(..., description="Type of fruit analyzed")
    device_id: Optional[str] = Field(None, description="Source device ID")
    run_id: UUID = Field(..., description="Unique identifier for the run")  # ? UUID instead of str
    cnt_total: conint(ge=0) = Field(..., description="Total fruit count in window")
    cnt_ripe: conint(ge=0) = Field(..., description="Ripe fruit count")
    cnt_unripe: conint(ge=0) = Field(..., description="Unripe fruit count")
    cnt_overripe: conint(ge=0) = Field(..., description="Overripe fruit count")
    pct_ripe: confloat(ge=0, le=1) = Field(..., description="Ripe ratio (0–1)")


class RipenessWeeklyRollupCreate(RipenessWeeklyRollupBase):
    """Schema used for POST inserts (single or batch)."""
    pass


class RipenessWeeklyRollupRead(RipenessWeeklyRollupBase):
    """Schema used for GET responses (includes DB ID)."""
    id: int = Field(..., description="Primary key ID")

    class Config:
        orm_mode = True

class RipenessWeeklyRollupOut(RipenessWeeklyRollupBase):
    """Schema for API responses (alias of Read)."""
    pass
