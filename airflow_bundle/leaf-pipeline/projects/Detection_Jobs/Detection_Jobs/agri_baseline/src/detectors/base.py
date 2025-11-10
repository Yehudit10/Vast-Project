from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Protocol


@dataclass(frozen=True)
class Detection:
    """
    Model-agnostic detection container.

    Canonical storage:
      - bbox: (x, y, w, h) in pixel coordinates.
      - confidence: float in [0, 1].
      - label: class/code string.

    Notes:
      - Properties expose a stable attribute API (.x/.y/.w/.h/.area etc.)
        so downstream code can use either bbox or attributes.
      - The class is frozen (immutable) to avoid accidental mutations
        during processing and logging.
    """
    label: str
    confidence: float
    bbox: Tuple[float, float, float, float]
    meta: Optional[Dict] = None  # optional extra data (e.g., model logits)

    # ---- Convenience constructors -------------------------------------------------

    @staticmethod
    def from_xywh(
        label: str,
        confidence: float,
        x: float,
        y: float,
        w: float,
        h: float,
        meta: Optional[Dict] = None,
    ) -> "Detection":
        """Create a Detection from explicit x/y/w/h values."""
        return Detection(label=label, confidence=float(confidence), bbox=(x, y, w, h), meta=meta)

    # ---- Attribute-style view over bbox ------------------------------------------

    @property
    def x(self) -> float:
        return float(self.bbox[0])

    @property
    def y(self) -> float:
        return float(self.bbox[1])

    @property
    def w(self) -> float:
        return float(self.bbox[2])

    @property
    def h(self) -> float:
        return float(self.bbox[3])

    @property
    def xmin(self) -> float:
        return self.x

    @property
    def ymin(self) -> float:
        return self.y

    @property
    def xmax(self) -> float:
        return self.x + self.w

    @property
    def ymax(self) -> float:
        return self.y + self.h

    @property
    def area(self) -> float:
        # Clamp at zero to avoid negative area if w/h are negative by mistake.
        return max(0.0, self.w) * max(0.0, self.h)


class Detector(Protocol):
    """
    Base detector interface.

    Implementors must return a list of Detection objects given a BGR image
    (numpy array with shape (H, W, 3), dtype=uint8).
    """
    name: str

    def run(self, bgr_image) -> List[Detection]:
        """Run inference on a BGR image and return model detections."""
        ...
