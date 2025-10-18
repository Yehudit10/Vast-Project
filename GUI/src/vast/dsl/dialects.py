"""SQL dialect abstraction.

Each dialect decides:
- how to quote identifiers (tables/columns),
- how to normalize Python booleans to DB-native values,
- and what placeholder syntax to use for bound parameters.
"""


from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class Dialect(ABC):
    @abstractmethod
    def quote_ident(self, name: str) -> str: 
        """Quote an identifier, supporting dotted paths like schema.table or table.column."""
        ...
    @abstractmethod
    def normalize_bool(self, v: Any) -> Any:
        """Convert Python bools to dialect-appropriate values (e.g., 0/1 for SQLite)."""
        ...
    @abstractmethod
    def placeholder(self, idx: int) -> str:
        """Return a placeholder string for the given 1-based parameter index."""
        ...  

class SQLiteDialect(Dialect):
    def quote_ident(self, name: str) -> str:
        parts = name.split(".")
        return ".".join('"' + p.replace('"', '""') + '"' for p in parts)
    def normalize_bool(self, v: Any) -> Any:
        return int(v) if isinstance(v, bool) else v
    def placeholder(self, idx: int) -> str:
        return "?"  # qmark style

class PostgresDialect(Dialect):
    def __init__(self, style: str = "psycopg"):
        """style:
        - 'psycopg'  → %s style placeholders (psycopg2/3)
        - 'numeric'  → $1, $2, ... style placeholders (asyncpg)
        """
        
        if style not in ("psycopg", "numeric"):
            raise ValueError("PostgresDialect.style must be 'psycopg' or 'numeric'")
        self.style = style
    def quote_ident(self, name: str) -> str:
        parts = name.split(".")
        return ".".join('"' + p.replace('"', '""') + '"' for p in parts)
    def normalize_bool(self, v: Any) -> Any:
        return v  # PostgreSQL has a real boolean type
    def placeholder(self, idx: int) -> str:
        return "%s" if self.style == "psycopg" else f"${idx}"