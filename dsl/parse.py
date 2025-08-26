"""
String predicate parsing (e.g., "ts >= 5" or "name == 'sensor-1'").
Keeps parsing concerns separate from the AST definitions.
"""

from __future__ import annotations
import re
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

_INT_RE = re.compile(r"^-?\d+$")
# Floats: 1.0, .5, 5., 1e3, -2.5E-4, etc.
_FLOAT_RE = re.compile(r"^-?(?:\d+\.\d*|\d*\.\d+|\d+)(?:[eE][+-]?\d+)?$")

def _unquote(s: str) -> str:
    """Remove surrounding single/double quotes if present; unescape common sequences."""
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        body = s[1:-1]
        # Minimal, safe unescape: handle common escapes without over-decoding
        body = body.replace(r"\\", "\\").replace(r"\'", "'").replace(r"\"", '"').replace(r"\n", "\n").replace(r"\t", "\t").replace(r"\r", "\r")
        return body
    return s

def _parse_term(term_raw: str):
    """
    Convert a token to a Field or primitive:
    - Quoted strings -> str (unescaped)
    - Booleans/null -> bool/None
    - Integers/floats -> int/float
    - Identifiers -> Field
    - Else -> str
    """
    s = term_raw.strip()

    # Quoted string → string literal
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return _unquote(s)

    # Booleans / null-ish (lowercase recommended; accept Pythonic 'None' too)
    if s in ("True", "False"):
        return s == "True"
    if s in ("null", "None"):
        return None

    # Numbers
    if _INT_RE.fullmatch(s):
        return int(s)
    if _FLOAT_RE.fullmatch(s):
        try:
            return float(s)
        except ValueError:
            pass  # fall through to identifier/string

    # Identifier → Field
    if _FIELD_RE.fullmatch(s):
        return Field(s)

    # Fallback → treat as bare string literal
    return _unquote(s)

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
