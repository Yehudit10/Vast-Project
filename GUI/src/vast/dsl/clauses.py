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
    def phase(self) -> str:
        return "select"

    def keyword(self) -> str:
        return "SELECT"

    def joiner(self) -> str:
        return ", "

    def fragment(self, ctx: CompileCtx) -> str:
        def star_aware_quote(col: str) -> str:
            # Skip quoting if expression or alias (COUNT(*), AVG(...), AS, etc.)
            if any(token in col.upper() for token in ("(", ")", " AS ")):
                return col  # treat as SQL expression

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


@dataclass
class OrderByClause(Clause):
    columns: list[str]
    directions: list[str]

    @property
    def phase(self): return "order_by"
    def keyword(self): return "ORDER BY"
    def joiner(self): return ", "

    def fragment(self, ctx):
        def quote_or_passthrough(col: str) -> str:
            # Skip quoting if it's clearly an SQL expression or aggregate
            if any(token in col.upper() for token in (
                "(", ")", " AS ", "COUNT", "AVG", "SUM", "MAX", "MIN"
            )):
                return col  # leave expressions as-is
            return ctx.dialect.quote_ident(col)

        cols = [quote_or_passthrough(c) for c in self.columns]
        dirs = self.directions or ["ASC"] * len(cols)
        return ", ".join(f"{c} {d.upper()}" for c, d in zip(cols, dirs))



@dataclass
class LimitClause(Clause):
    limit: int
    @property
    def phase(self): return "limit"
    def keyword(self): return "LIMIT"
    def joiner(self): return " "
    def fragment(self, ctx): return str(self.limit)


@dataclass
class OffsetClause(Clause):
    offset: int
    @property
    def phase(self): return "offset"
    def keyword(self): return "OFFSET"
    def joiner(self): return " "
    def fragment(self, ctx): return str(self.offset)


@dataclass
class GroupByClause(Clause):
    columns: list[str]

    @property
    def phase(self): return "group_by"
    def keyword(self): return "GROUP BY"
    def joiner(self): return ", "

    def fragment(self, ctx):
        def quote_or_passthrough(col: str) -> str:
            # Skip quoting if it's a SQL expression or function call
            if any(token in col.upper() for token in (
                "(", ")", " AS ", "COUNT", "AVG", "SUM", "MAX", "MIN", "DATE_TRUNC"
            )):
                return col
            return ctx.dialect.quote_ident(col)
        return ", ".join(quote_or_passthrough(c) for c in self.columns)



@dataclass
class HavingClause(Clause):
    cond: Cond
    @property
    def phase(self): return "having"
    def keyword(self): return "HAVING"
    def joiner(self): return " AND "
    def fragment(self, ctx): return self.cond.compile(ctx)
