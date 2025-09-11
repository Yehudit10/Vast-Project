from dataclasses import dataclass
from typing import Literal, Optional, Tuple

TileScheme = Literal["XYZ", "TMS"]

@dataclass(frozen=True)
class Sensor:
    id: str
    lon: float
    lat: float
    value: Optional[float] = None
    label: Optional[str] = None

# Optional: screen / scene points for Qt,
PointF = Tuple[float, float]
