from dataclasses import dataclass, field
from typing import Optional, Dict
from datetime import datetime

@dataclass
class Event:
    ts: datetime
    device_id: str
    sensor_type: str
    site_id: Optional[str]
    msg_type: str          # "reading" | "keepalive"
    value: Optional[float]
    seq: Optional[int]
    quality: Optional[str] # "ok"/"corrupted"/None

@dataclass
class Alert:
    device_id: str
    issue_type: str
    start_ts: datetime
    end_ts: Optional[datetime]
    severity: str
    sensor_type: Optional[str] = None
    site_id: Optional[str] = None
    details: Dict = field(default_factory=dict)

@dataclass
class DeviceState:
    device_id: str
    sensor_type: Optional[str] = None
    last_seen_ts: Optional[datetime] = None
    last_value: Optional[float] = None
    run_length: int = 0
    stuck_since_ts: Optional[datetime] = None
    open_alerts: Dict[str, "Alert"] = field(default_factory=dict)
