"""SQL builder pipeline.

1) SQLBuilder.compile takes a Plan or dict, instantiates SQLState with a dialect.
2) For each item in plan._ops, it looks up the Op subclass in the registry and applies it.
3) SQLState.build:
   - injects FROM (always required) and a default SELECT if missing,
   - renders phases in a stable order (SELECT → FROM → WHERE),
   - collects the final SQL string and the bound params from CompileCtx.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
from collections import defaultdict
from .dialects import Dialect, SQLiteDialect
from .runtime import CompileCtx
from .clauses import Clause, SelectClause, FromClause, WhereClause
from .ops import Op, SelectOp, WhereOp  # ensure registry
from .ir import Plan

@dataclass
class SQLState:
    """Mutable assembly state for a single SQL statement."""
    source: str
    dialect: Dialect
    clauses: Dict[str, List[Clause]] = field(default_factory=lambda: defaultdict(list))
    CLAUSE_ORDER: List[str] = field(default_factory=lambda: [
    "select", "from", "where", "group_by", "having", "order_by", "limit", "offset"
])


    def add_clause(self, clause: Clause) -> None:
        self.clauses[clause.phase].append(clause)

    def has_phase(self, name: str) -> bool:
        return name in self.clauses and len(self.clauses[name]) > 0

    def build(self) -> tuple[str, List[Any]]:
        """Render all collected clauses into a SQL string and parameter list."""
        ctx = CompileCtx(self.dialect)
        parts: List[str] = []

        # Ensure FROM exists for this plan
        self.add_clause(FromClause(self.source))
        # Ensure SELECT exists (default "*") if none provided
        if not self.has_phase("select"):
            self.add_select(["*"])

        # Render ordered phases, then any extras not in the order list
        seen = set()
        def render_phase(phase: str):
            items = self.clauses.get(phase, [])
            if not items: return
            kw = items[0].keyword()
            joiner = items[0].joiner()
            frags = [c.fragment(ctx) for c in items]
            if frags: parts.append(f"{kw} {joiner.join(frags)}")
            seen.add(phase)

        for ph in self.CLAUSE_ORDER: render_phase(ph)
        for ph in list(self.clauses.keys()):
            if ph not in seen: render_phase(ph)

        sql = " ".join(parts)
        return sql, ctx.params

class SQLBuilder:
    """Facade that compiles a strict Plan (or dict) into (sql, params) using a dialect."""
    def __init__(self, dialect: Dialect | None = None) -> None:
        self.dialect = dialect or SQLiteDialect()
    def compile(self, plan: Plan | Dict[str, Any]) -> tuple[str, List[Any]]:
        """Validate ops, apply them to SQLState, and produce final SQL + params."""
        p = plan if isinstance(plan, Plan) else Plan.from_dict(plan)
        st = SQLState(source=p.source, dialect=self.dialect)
        for op in p._ops:
            if not isinstance(op, dict):
                raise TypeError(f"Each operation must be a dict, got {type(op).__name__}: {op}")

            allowed_keys = {"op", "columns", "cond", "directions", "limit", "offset"}
            extra = set(op.keys()) - allowed_keys
            if extra:
                raise ValueError(f"Unknown keys in op: {op}")

            op_type = op.get("op")
            if op_type not in Op.registry:
                raise ValueError(f"Unsupported op {op_type!r}. Allowed: {sorted(Op.registry)}")

            # Pass all keys except "op" as kwargs
            Op.registry[op_type](**{k: v for k, v in op.items() if k != "op"}).apply(st)

        return st.build()
