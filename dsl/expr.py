"""
AST node definitions: Expr, Field, Literal, Predicate, and Operator enum.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class Operator(str, Enum):
    """Binary comparison operators supported by the DSL."""
    GT = ">"
    LT = "<"
    GE = ">="
    LE = "<="
    EQ = "=="
    NE = "!="


class Expr:
    """
    Base class for AST nodes that can be serialized to a JSON-serializable dict via `to_plan()`.
    """
    def to_plan(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation of this node."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Literal(Expr):
    """Literal value node (wraps Python primitives)."""
    value: Any
    def to_plan(self) -> Dict[str, Any]:
        return {"literal": self.value}


@dataclass(frozen=True, slots=True)
class Field(Expr):
    """
    Field reference node (column/identifier).
    Supports dotted notation like 'table.column'.
    """
    name: str

    # Build Predicate AST via Python comparison operators
    def __gt__(self, other):  # field > other
        return Predicate(Operator.GT, self, other)
    def __lt__(self, other):  # field < other
        return Predicate(Operator.LT, self, other)
    def __ge__(self, other):  # field >= other
        return Predicate(Operator.GE, self, other)
    def __le__(self, other):  # field <= other
        return Predicate(Operator.LE, self, other)
    def __ne__(self, other):  # field != other
        return Predicate(Operator.NE, self, other)
    def __eq__(self, other):  # field == other
        return Predicate(Operator.EQ, self, other)

    def to_plan(self) -> Dict[str, Any]:
        return {"field": self.name}


@dataclass(slots=True)
class Predicate(Expr):
    """
    A simple binary predicate: <lhs> <op> <rhs>

    Examples (Python-building):
      Field("ts") > 1700000000
      Field("name") == "sensor-1"
    """
    op: Operator                  # one of ">", "<", ">=", "<=", "==", "!="
    lhs: Expr                     # e.g., Field("ts")
    rhs: Expr                     # e.g., Literal(123) or Field("other")

    def __init__(self, op: Operator, lhs: Any, rhs: Any):
        if not isinstance(op, Operator):
            raise TypeError(f"op must be Operator, got {type(op).__name__}")
        if not isinstance(lhs, Expr):
            lhs = Literal(lhs)
        if not isinstance(rhs, Expr):
            rhs = Literal(rhs)
        self.op = op
        self.lhs = lhs
        self.rhs = rhs

    def __repr__(self) -> str:
        return f"Predicate({self.op.value}, {self.lhs!r}, {self.rhs!r})"

    def to_plan(self) -> Dict[str, Any]:
        """Serialize predicate to the JSON plan fragment."""
        return {
            "op": self.op.value,
            "lhs": self.lhs.to_plan(),
            "rhs": self.rhs.to_plan(),
        }