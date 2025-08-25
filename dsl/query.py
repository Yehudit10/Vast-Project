"""
Query builder and plan serialization.
"""

from __future__ import annotations
import json
from dataclasses import dataclass, field as dc_field
from typing import Any, Dict, List, Union
from .expr import Expr
from .parse import parse_predicate


@dataclass(slots=True)
class Operation:
    """
    One plan step, e.g.:
      {"op": "select", "fields": ["a", "b"]}
      {"op": "filter", "predicate": {...}}
    """
    kind: str
    args: Dict[str, Any] = dc_field(default_factory=dict)

    def to_plan(self) -> Dict[str, Any]:
        """Serialize operation to the JSON plan fragment."""
        return {"op": self.kind, **self.args}


@dataclass
class Query:
    """
    Query is a mutable builder that accumulates operations (select, filter, ...).

    Typical usage:
      plan_json = (
          Query()
            .select("sensor", "ts", "value")
            .where("ts >= 5")           # or .where(Field("ts") >= 5)
            .to_json(pretty=True)
      )
    """
    _ops: List[Operation] = dc_field(default_factory=list)

    def clone(self) -> "Query":
        """Return a shallow copy that can be safely mutated independently."""
        return Query(list(self._ops))

    def select(self, *fields: str) -> "Query":
        """
        Add a projection step. You must pass at least one field.
        You can also pass a single list/tuple of fields: select(["a", "b"]).
        """
        if not fields:
            raise ValueError("select() requires at least one field")
        if len(fields) == 1 and isinstance(fields[0], (list, tuple)):
            fields = tuple(fields[0])
        
        self._ops.append(Operation("select", {"fields": list(fields)}))
        return self

    def where(self, predicate: Union[str, Expr]) -> "Query":
        """
        Add a filtering step. Accepts:
          - a string predicate (parsed via `parse_predicate`)
          - an Expr (typically a Predicate built via Field() operators)
        """
        pred = parse_predicate(predicate) if isinstance(predicate, str) else predicate
        if not isinstance(pred, Expr):
            raise ValueError(f"Unsupported predicate: {predicate!r}")
        self._ops.append(Operation("filter", {"predicate": pred.to_plan()}))
        return self

    def to_plan(self) -> Dict[str, Any]:
        """Return the full execution plan as a JSON-serializable dict."""
        return {"ops": [op.to_plan() for op in self._ops]}

    def to_json(self, *, pretty: bool = False) -> str:
        """Return the execution plan as a JSON string."""
        plan = self.to_plan()
        if pretty:
            return json.dumps(plan, indent=2, ensure_ascii=False)
        return json.dumps(plan, separators=(",", ":"), ensure_ascii=False)

    def reset(self) -> "Query":
        """
        Clear all accumulated operations on this Query *in place* and
        return self so you can keep chaining.
        """
        self._ops.clear()
        return self