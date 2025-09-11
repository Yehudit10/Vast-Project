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
    
    def to_plan(self) -> Plan:
        """Return the underlying Plan object (e.g., for transport)."""
        return self._plan
    
    def to_sql(self, dialect: Dialect | None = None):
        """Compile the plan with the chosen dialect (SQLite by default)."""
        return SQLBuilder(dialect).compile(self._plan)