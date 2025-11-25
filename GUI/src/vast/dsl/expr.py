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

    def compile(self, ctx: CompileCtx) -> str:
        # Detect SQL expressions that should be inlined (not parameterized)
        if isinstance(self.value, str) and any(
            kw in self.value.lower()
            for kw in ("now()", "interval", "date_trunc", "current_date", "current_timestamp")
        ):
            return self.value  # inline directly as SQL expression

        # Default: treat as bound parameter
        return ctx.add_param(self.value)

    def to_ir(self) -> Dict[str, Any]:
        return {"literal": self.value}

@dataclass
class Func(Expr):
    name: str
    args: list[Expr]

    def compile(self, ctx: CompileCtx) -> str:
        compiled = ", ".join(arg.compile(ctx) for arg in self.args)
        return f"{self.name.upper()}({compiled})"

    def to_ir(self) -> Dict[str, Any]:
        return {
            "func": self.name,
            "args": [arg.to_ir() for arg in self.args]
        }



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
        if not isinstance(self.left, (Col, Literal,Func)) or not isinstance(self.right, (Col, Literal,Func)):
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
    if not isinstance(d, dict):
        raise TypeError("Expr leaf must be an object")

    keys = set(d.keys())

    if keys == {"col"}:
        return Col(d["col"])

    if keys == {"literal"}:
        return Literal(d["literal"])

    if keys == {"func", "args"}:
        return Func(
            d["func"],
            [expr_from_ir(arg) for arg in d["args"]]
        )

    raise ValueError(f"Invalid Expr IR: {d}")



def cond_from_ir(d: Dict[str, Any]) -> Cond:
    """Decode a strict Cond IR object into Cond with defensive validation."""
    # ───────────── DEBUG LOG ─────────────
    import traceback
    print("\n[DEBUG cond_from_ir] called with:", repr(d))
    # Optional: print call stack to see which Op invoked this
    # print("".join(traceback.format_stack(limit=3)))

    if not isinstance(d, dict):
        raise TypeError(f"Cond node must be an object, got {type(d).__name__}: {d}")

    keys = set(d.keys())

    # ───── Logical AND
    if keys == {"all"}:
        arr = d["all"]
        if not isinstance(arr, list):
            raise TypeError(f"'all' must be a list of condition objects, got {type(arr).__name__}")
        for i, item in enumerate(arr):
            if not isinstance(item, dict):
                raise TypeError(f"List argument at index {i} must be a dict, got {type(item).__name__}: {item}")
        return All(*[cond_from_ir(x) for x in arr])

    # ───── Logical OR
    if keys == {"any"}:
        arr = d["any"]
        if not isinstance(arr, list):
            raise TypeError(f"'any' must be a list of condition objects, got {type(arr).__name__}")
        for i, item in enumerate(arr):
            if not isinstance(item, dict):
                raise TypeError(f"List argument at index {i} must be a dict, got {type(item).__name__}: {item}")
        return Any(*[cond_from_ir(x) for x in arr])

    # ───── Predicate
    if keys == {"op", "left", "right"}:
        try:
            op = BinOp(d["op"])
        except ValueError as e:
            allowed = ", ".join(o.value for o in BinOp)
            raise ValueError(f"Operator {d['op']!r} not allowed. Allowed: [{allowed}]") from e
        return Predicate(expr_from_ir(d["left"]), op, expr_from_ir(d["right"]))

    if "col" in d and "literal" in d:
        return Predicate(expr_from_ir({"col": d["col"]}), BinOp.EQ, expr_from_ir({"literal": d["literal"]}))

    raise ValueError(f"Invalid condition node: {d}")



# Convenience aliases
AND = All
OR = Any
