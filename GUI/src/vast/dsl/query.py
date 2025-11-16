"""Fluent, chainable Python DSL that produces a strict Plan and compiles to SQL.

Example:
    q = Query("sensors").select("sensor_id").where(Col("status") == "ok")
    sql, params = q.to_sql()
"""

from __future__ import annotations
from .ir import Plan
from .expr import Cond
from .builder import SQLBuilder
from .dialects import Dialect
from typing import List, Tuple

class Query:
    def __init__(self, source: str):
        self._plan = Plan(source=source)

    def select(self, *columns: str) -> "Query":
        """Add a SELECT op (empty → '*')."""
        self._plan._ops.append({"op": "select", "columns": list(columns)})
        return self
    
    def where(self, cond: Cond) -> "Query":
        """Add a WHERE op by serializing the Cond tree to strict IR."""
        self._plan._ops.append({"op": "where", "cond": cond.to_ir()})
        return self
    
    def order_by(self, *columns: str, directions: list[str] | None = None) -> "Query":
        directions = directions or ["ASC"] * len(columns)
        self._plan._ops.append({"op": "order_by", "columns": list(columns), "directions": directions})
        return self

    def limit(self, n: int) -> "Query":
        self._plan._ops.append({"op": "limit", "limit": n})
        return self

    def offset(self, n: int) -> "Query":
        self._plan._ops.append({"op": "offset", "offset": n})
        return self

    def group_by(self, *columns: str) -> "Query":
        self._plan._ops.append({"op": "group_by", "columns": list(columns)})
        return self

    def having(self, cond: Cond) -> "Query":
        self._plan._ops.append({"op": "having", "cond": cond.to_ir()})
        return self

    
    def to_plan(self) -> Plan:
        """Return the underlying Plan object (e.g., for transport)."""
        return self._plan
    
    def to_sql(self, dialect: Dialect | None = None):
        """Compile the plan with the chosen dialect (SQLite by default)."""
        return SQLBuilder(dialect).compile(self._plan)