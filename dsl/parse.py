"""
String predicate parsing (e.g., "ts >= 5" or "name == 'sensor-1'").
Keeps parsing concerns separate from the AST definitions.
"""

from __future__ import annotations
import re
from typing import Any
from .expr import Field, Predicate, Operator

# Identifiers: allow dotted names like table.column, no dashes/spaces.
_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")

# Tokens and operators (longest first so >= matches before >).
_TOKEN = r"(?:[-A-Za-z0-9_.]+|'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
_OP_PATTERN = "|".join(sorted((re.escape(op.value) for op in Operator), key=len, reverse=True))

# Also accept "=" as alias for "==".
_PREDICATE_RE = re.compile(
    rf"^(?P<lhs>{_TOKEN})\s*(?P<op>{_OP_PATTERN}|=)\s*(?P<rhs>{_TOKEN})$"
)


def _unquote(s: str) -> str:
    """Remove surrounding single/double quotes if present; unescape common sequences."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        body = s[1:-1]
        return bytes(body, "utf-8").decode("unicode_escape")
    return s


def _parse_term(term_raw: str) -> Any:
    """
    Convert a token to a Field or primitive:
    - Identifiers -> Field
    - Quoted strings -> str (unescaped)
    - Integers/floats -> int/float
    - Else -> str
    """
    if _FIELD_RE.match(term_raw):
        return Field(term_raw)

    s = _unquote(term_raw)

    if re.fullmatch(r"-?\d+", s):
        return int(s)
    if re.fullmatch(r"-?\d+\.\d+", s):
        return float(s)
    return s


def parse_predicate(expr: str) -> Predicate:
    """
    Parse "<TOKEN> <OP> <TOKEN>" into a Predicate.

    TOKEN:
      - bare words (letters/digits/_ and dots), e.g. table.col
      - single-quoted strings: 'a', 'a\\n'
      - double-quoted strings: "a", "a\\n"

    Operators:
      >=, <=, ==, !=, >, <   (and '=' which is normalized to '==')
    """
    m = _PREDICATE_RE.match(expr.strip())
    if not m:
        raise ValueError(
            f"Unsupported predicate syntax: {expr!r}. "
            f"Expected: <token> <op> <token> where op in "
            f"{[o.value for o in Operator]} (also '=' as alias for '==')."
        )

    op_symbol = "==" if m.group("op") == "=" else m.group("op")
    return Predicate(
        op=Operator(op_symbol),
        lhs=_parse_term(m.group("lhs").strip()),
        rhs=_parse_term(m.group("rhs").strip()),
    )