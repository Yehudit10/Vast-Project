"""Expression and condition trees for the DSL.

Two layers:
- Expr: scalar leaves (columns, literals) used inside predicates.
- Cond: boolean expressions (AND/OR/predicates) used in WHERE.

We purposely restrict binary predicates to compare only Col and Literal
to keep compilation and parameterization simple and safe.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict
from abc import ABC, abstractmethod
from .runtime import CompileCtx
from .binops import BinOp

ALLOWED_BIN_OPS = {"=", "!=", "<", "<=", ">", ">="}

class Expr(ABC):
    @abstractmethod
    def compile(self, ctx: CompileCtx) -> str:
        """Render this scalar expression to SQL, possibly producing a placeholder."""
        ...

    @abstractmethod
    def to_ir(self) -> Dict[str, Any]:
        """Serialize to strict JSON IR (e.g., {'col': 'name'} or {'literal': 42})."""
        ...

    # Operator sugar → Predicate
    def __eq__(self, other: Any) -> "Predicate": return Predicate(self, BinOp.EQ, ensure_expr(other))
    def __ne__(self, other: Any) -> "Predicate": return Predicate(self, BinOp.NE, ensure_expr(other))
    def __lt__(self, other: Any) -> "Predicate": return Predicate(self, BinOp.LT, ensure_expr(other))
    def __le__(self, other: Any) -> "Predicate": return Predicate(self, BinOp.LE, ensure_expr(other))
    def __gt__(self, other: Any) -> "Predicate": return Predicate(self, BinOp.GT, ensure_expr(other))
    def __ge__(self, other: Any) -> "Predicate": return Predicate(self, BinOp.GE, ensure_expr(other))

@dataclass
class Col(Expr):
    """A column reference (optionally dotted, e.g., 'schema.table' or 'table.col')."""
    name: str
    def compile(self, ctx: CompileCtx) -> str: return ctx.dialect.quote_ident(self.name)
    def to_ir(self) -> Dict[str, Any]: return {"col": self.name}

@dataclass
class Literal(Expr):
    """A literal value that becomes a bound parameter (with a placeholder)."""
    value: Any
    def compile(self, ctx: CompileCtx) -> str: return ctx.add_param(self.value)
    def to_ir(self) -> Dict[str, Any]: return {"literal": self.value}

def ensure_expr(x: Any) -> Expr:
    """Coerce Python values to Literal, leave Expr as-is."""
    return x if isinstance(x, Expr) else Literal(x)

# ---- Boolean conditions ----
class Cond(ABC):
    @abstractmethod
    def compile(self, ctx: CompileCtx) -> str:
        """Render this boolean condition to SQL text."""
        ...
    @abstractmethod
    def to_ir(self) -> Dict[str, Any]:
        """Serialize to strict JSON IR."""
        ...

@dataclass
class Predicate(Cond):
    """Binary predicate: (left <op> right)."""
    left: Expr
    op: BinOp
    right: Expr
    def __post_init__(self):
        if not isinstance(self.left, (Col, Literal)) or not isinstance(self.right, (Col, Literal)):
            raise TypeError("Predicate must compare columns and/or literals only")
    def compile(self, ctx: CompileCtx) -> str:
        return f"({self.left.compile(ctx)} {self.op.value} {self.right.compile(ctx)})"
    def to_ir(self) -> Dict[str, Any]:
        return {"op": self.op.value, "left": self.left.to_ir(), "right": self.right.to_ir()}


class All(Cond):  # AND
    parts: list[Cond]
    def __init__(self, *parts: Cond): self.parts = list(parts)
    def compile(self, ctx: CompileCtx) -> str: return "(" + " AND ".join(p.compile(ctx) for p in self.parts) + ")"
    def to_ir(self) -> Dict[str, Any]: return {"all": [p.to_ir() for p in self.parts]}


class Any(Cond):  # OR
    parts: list[Cond]
    def __init__(self, *parts: Cond): self.parts = list(parts)
    def compile(self, ctx: CompileCtx) -> str: return "(" + " OR ".join(p.compile(ctx) for p in self.parts) + ")"
    def to_ir(self) -> Dict[str, Any]: return {"any": [p.to_ir() for p in self.parts]}

# ---- Strict IR decoding ----

def expr_from_ir(d: Dict[str, Any]) -> Expr:
    """Decode a strict Expr IR object into Expr."""
    if not isinstance(d, dict): raise TypeError("Expr leaf must be an object")
    keys = set(d.keys())
    if keys == {"col"}: return Col(d["col"])
    if keys == {"literal"}: return Literal(d["literal"])
    raise ValueError("Expr leaf must be either {\"col\": name} or {\"literal\": value}")


def cond_from_ir(d: Dict[str, Any]) -> Cond:
    """Decode a strict Cond IR object into Cond."""
    if not isinstance(d, dict): raise TypeError("Cond node must be an object")
    keys = set(d.keys())
    if keys == {"all"}:
        arr = d["all"]
        if not isinstance(arr, list): raise TypeError("all must be an array of Cond")
        return All(*[cond_from_ir(x) for x in arr])
    if keys == {"any"}:
        arr = d["any"]
        if not isinstance(arr, list): raise TypeError("any must be an array of Cond")
        return Any(*[cond_from_ir(x) for x in arr])
    if keys == {"op", "left", "right"}:
        try:
            op = BinOp(d["op"])  # raises ValueError if unknown -> nice error
        except ValueError as e:
            allowed = ", ".join(o.value for o in BinOp)
            raise ValueError(f"Operator {d['op']!r} not allowed. Allowed: [{allowed}]") from e
        return Predicate(expr_from_ir(d["left"]), op, expr_from_ir(d["right"]))

# Convenience aliases
AND = All
OR = Any