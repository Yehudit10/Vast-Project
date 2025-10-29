from typing import Optional
from pydantic import BaseModel, Field, confloat # type: ignore

class TaskThresholdCreate(BaseModel):
    task: str                     # e.g. "ripeness", "disease"
    label: str = Field(default="")  # optional sub-type; empty = default bucket
    threshold: confloat(ge=0, le=1)
    updated_by: Optional[str] = None

class TaskThresholdUpdate(BaseModel):
    task: Optional[str] = None       # allow renaming if needed (rare)
    label: Optional[str] = None
    threshold: Optional[confloat(ge=0, le=1)] = None
    updated_by: Optional[str] = None
