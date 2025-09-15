"""Public package surface for the DSL.

Re-exports the most common types so users can do:
    from dsl import Query, Col, Literal, AND, OR, SQLBuilder, SQLiteDialect, PostgresDialect
"""

from __future__ import annotations
from .dialects import Dialect, SQLiteDialect, PostgresDialect
from .expr import Expr, Col, Literal, Predicate, Cond, AND, OR, ALLOWED_BIN_OPS
from .ir import Plan
from .builder import SQLBuilder
from .query import Query


__all__ = [
    "Dialect", "SQLiteDialect", "PostgresDialect",
    "Expr", "Col", "Literal", "Predicate", "Cond", "AND", "OR", "ALLOWED_BIN_OPS",
    "Plan", "SQLBuilder", "Query",
]