from dataclasses import dataclass
from typing import Optional, Dict
from datetime import datetime

@dataclass
class Alert:
    entity_id: str
    rule: str
    window_start: datetime
    window_end: datetime
    score: float
    first_seen: datetime
    last_seen: datetime
    status: str  # OPEN | ACK | RESOLVED
    meta: Dict
