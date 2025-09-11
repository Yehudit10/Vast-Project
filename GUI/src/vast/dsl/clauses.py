"""Low-level SQL clause objects.

Each Clause knows:
- its logical phase (e.g., 'select', 'from', 'where'),
- how to render its keyword and fragment,
- and how to join multiple instances within the same phase.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List
from abc import ABC, abstractmethod
from .runtime import CompileCtx
from .expr import Cond

class Clause(ABC):
    @property
    @abstractmethod
    def phase(self) -> str: ...            # e.g., "select", "from", "where", "order_by"
    @abstractmethod
    def keyword(self) -> str: ...          # e.g., "SELECT", "FROM", "WHERE"
    @abstractmethod
    def joiner(self) -> str: ...           # how to join multiple fragments in same phase
    @abstractmethod
    def fragment(self, ctx: CompileCtx) -> str: ...

@dataclass
class SelectClause(Clause):
    columns: List[str]
    @property
    def phase(self) -> str: return "select"
    def keyword(self) -> str: return "SELECT"
    def joiner(self) -> str: return ", "
    def fragment(self, ctx: CompileCtx) -> str:
        def star_aware_quote(col: str) -> str:
            # Support "*", "tbl.*", and dotted names that may end with *
            parts = col.split(".")
            quoted = []
            for p in parts:
                if p == "*":
                    quoted.append("*")
                else:
                    quoted.append(ctx.dialect.quote_ident(p))
            return ".".join(quoted)
        if not self.columns:
            return "*"  # default
        return ", ".join(star_aware_quote(c) for c in self.columns)


@dataclass
class FromClause(Clause):
    source: str
    @property
    def phase(self) -> str: return "from"
    def keyword(self) -> str: return "FROM"
    def joiner(self) -> str: return " "
    def fragment(self, ctx: CompileCtx) -> str:
        return ctx.dialect.quote_ident(self.source)

@dataclass
class WhereClause(Clause):
    cond: Cond
    @property
    def phase(self) -> str: return "where"
    def keyword(self) -> str: return "WHERE"
    def joiner(self) -> str: return " AND "
    def fragment(self, ctx: CompileCtx) -> str:
        return self.cond.compile(ctx)