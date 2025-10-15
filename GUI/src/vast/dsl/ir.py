from __future__ import annotations
"""Strict JSON IR container for query plans.

A Plan is intentionally minimal: a source (table/view) and a list of ops.
Serialization uses a stable shape to keep validation simple.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

@dataclass
class Plan:
    source: str
    _ops: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a minimal, stable dict shape."""
        return {"source": self.source, "_ops": self._ops}

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Plan":
        """Validate and construct a Plan from a dict."""
        if set(d.keys()) != {"source", "_ops"}:
            raise ValueError("Plan must contain exactly 'source' and '_ops'")
        return Plan(source=d["source"], _ops=list(d.get("_ops", [])))