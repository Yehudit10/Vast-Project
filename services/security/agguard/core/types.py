from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple

BBox = Tuple[int, int, int, int]  # x1, y1, x2, y2

@dataclass
class Detection:
    cls: str
    conf: float
    bbox: BBox

@dataclass
class Track:
    track_id: int
    cls: str   # change to str to match aggregator expectations
    conf: float
    bbox: tuple  # (x1, y1, x2, y2)
    hits: int = 0
    miss: int = 0
