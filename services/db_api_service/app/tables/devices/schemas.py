from pydantic import BaseModel
from typing import Optional, List

class DeviceOut(BaseModel):
    device_id: str
    model: Optional[str] = None
    owner: Optional[str] = None
    active: Optional[bool] = None

class DeviceList(BaseModel):
    total: int
    items: List[DeviceOut]