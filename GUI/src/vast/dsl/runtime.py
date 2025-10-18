"""Compilation-time context.

Holds the evolving list of bound parameters and the active dialect,
and exposes a helper to push a parameter and get the correct placeholder.
"""
from __future__ import annotations
from typing import Any, List
from .dialects import Dialect

class CompileCtx:
    def __init__(self, dialect: Dialect) -> None:
        self.params: List[Any] = []   # Accumulated bound parameters in order of appearance.
        self.dialect = dialect

    def add_param(self, v: Any) -> str:
        """Append a value (after dialect-specific normalization) and return its placeholder."""
        self.params.append(self.dialect.normalize_bool(v))
        return self.dialect.placeholder(len(self.params))
