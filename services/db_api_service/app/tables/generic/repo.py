# app/tables/generic/repo.py
# DB-facing logic: reflection + validation + inserts (single/batch) + describe.

from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import date, datetime
from functools import lru_cache
import decimal
import uuid

from sqlalchemy import MetaData, insert, select, asc, desc
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


from app.db import engine, session_scope

# Configure allowed tables (can move to env/config later)
ALLOWED_TABLES = {"event_logs_sensors"}
STRICT_UNKNOWN_FIELDS = True

# Loads and caches SQLAlchemy table metadata for allowed tables.
@lru_cache(maxsize=1)
def load_metadata() -> MetaData:
    md = MetaData()
    md.reflect(bind=engine, only=list(ALLOWED_TABLES))
    return md

# Returns the SQLAlchemy table object for the given resource name.
def get_table(resource: str):
    md = load_metadata()
    return md.tables.get(resource)

# --- type mapping + validation (pydantic v1 style) ---

from pydantic import BaseModel, ValidationError, create_model

# Maps SQLAlchemy column types to Python types.
_SQLA_TO_PY = {
    "INTEGER": int, "BIGINT": int, "SMALLINT": int,
    "NUMERIC": decimal.Decimal, "DECIMAL": decimal.Decimal, "FLOAT": float,
    "UUID": uuid.UUID,
    "VARCHAR": str, "TEXT": str,
    "BOOLEAN": bool, "DATE": date, "TIMESTAMP": datetime,
    "JSON": dict,
}

# Returns the Python type for a SQLAlchemy column.
def _py_type(col) -> Any:
    return _SQLA_TO_PY.get(col.type.__class__.__name__.upper(), str)

# Dynamically builds a Pydantic model for validating insert requests for a given table.
def _build_insert_model(table):
    fields = {}
    for c in table.columns:
        py_t = _py_type(c)
        optional = c.primary_key or c.autoincrement or c.nullable or c.server_default is not None
        if optional:
            fields[c.name] = (Optional[py_t], None)  # type: ignore[valid-type]
        else:
            fields[c.name] = (py_t, ...)
    return create_model(f"{table.name.title()}Insert", **fields)

# Validates and cleans incoming payload data for a table insert.
def _validate(table, payload: Dict[str, Any]) -> Dict[str, Any]:
    Model = _build_insert_model(table)
    obj = Model(**payload)  # raises ValidationError on bad types
    return obj.dict(exclude_none=True)

# --- public repo API ---

# Base repo error with optional payload for HTTP layer.
class RepoError(Exception):
    def __init__(self, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.payload = payload or {}

# Raised when a table is not allowed or not found.
class NotAllowed(RepoError):
    pass

# Raised when validation fails.
class ValidationFailed(RepoError):
    pass

# Raised on database integrity errors (e.g., unique constraint).
class DbConstraintError(RepoError):
    pass

# Raised on general SQL/database errors.
class DbSqlError(RepoError):
    pass

# Returns the schema (columns and types) for a given table.
def describe_table(resource: str) -> dict:
    table = get_table(resource)
    if table is None:
        raise NotAllowed("table not allowed or not found")
    cols = []
    for c in table.columns:
        cols.append({
            "name": c.name,
            "type": c.type.__class__.__name__,
            "nullable": c.nullable,
            "primary_key": c.primary_key,
            "autoincrement": bool(getattr(c, "autoincrement", False)),
            "server_default": str(c.server_default.arg) if c.server_default is not None else None,
        })
    return {"table": table.name, "columns": cols}

# Inserts a single row into the specified table after validation.
def insert_one(resource: str, payload: Dict[str, Any], returning: str = "keys") -> dict:
    table = get_table(resource)
    if table is None:
        raise NotAllowed("table not allowed or not found")

    allowed_cols = {c.name for c in table.columns}
    if STRICT_UNKNOWN_FIELDS:
        unknown = set(payload) - allowed_cols
        if unknown:
            raise ValidationFailed("unknown fields", {"unknown_fields": sorted(unknown)})

    clean = {k: v for k, v in payload.items() if k in allowed_cols}
    try:
        valid = _validate(table, clean)
    except ValidationError as e:
        raise ValidationFailed("validation error", {"validation_error": e.errors()})

    with session_scope() as s:
        stmt = insert(table).values(**valid)
        if returning == "full":
            stmt = stmt.returning(*table.columns)
        elif table.primary_key:
            stmt = stmt.returning(*table.primary_key.columns)
        try:
            res = s.execute(stmt)
            row = res.mappings().first() if res.returns_rows else None
            return {"affected_rows": 1, "returning": dict(row) if row else None}
        except IntegrityError as e:
            raise DbConstraintError("integrity error", {"detail": str(e.orig)})
        except SQLAlchemyError as e:
            raise DbSqlError("sql error", {"detail": str(e)})

# Inserts multiple rows (batch) into the specified table after validation.
def insert_batch(resource: str, payloads: List[Dict[str, Any]]) -> dict:
    table = get_table(resource)
    if table is None:
        raise NotAllowed("table not allowed or not found")

    allowed_cols = {c.name for c in table.columns}
    to_insert = []
    try:
        for p in payloads:
            if STRICT_UNKNOWN_FIELDS:
                unknown = set(p) - allowed_cols
                if unknown:
                    raise ValidationFailed("unknown fields", {"unknown_fields": sorted(unknown)})
            clean = {k: v for k, v in p.items() if k in allowed_cols}
            to_insert.append(_validate(table, clean))
    except ValidationError as e:
        raise ValidationFailed("validation error", {"validation_error": e.errors()})

    with session_scope() as s:
        try:
            s.execute(insert(table), to_insert)
            return {"affected_rows": len(to_insert)}
        except IntegrityError as e:
            raise DbConstraintError("integrity error", {"detail": str(e.orig)})
        except SQLAlchemyError as e:
            raise DbSqlError("sql error", {"detail": str(e)})
def list_rows(
    resource: str,
    limit: int = 50,
    offset: int = 0,
    order_by: str | None = None,
    order_dir: str = "desc",
    filters: dict[str, object] | None = None,
) -> dict:
    table = get_table(resource)
    if table is None:
        raise NotAllowed("table not allowed or not found")

    # validate limit/offset
    limit = max(1, min(limit, 500))
    offset = max(0, offset)

    # validate columns for order_by & filters
    colmap = {c.name: c for c in table.columns}

    order_clause = None
    if order_by:
        if order_by not in colmap:
            raise ValidationFailed("unknown order_by", {"order_by": order_by})
        order_clause = asc(colmap[order_by]) if order_dir.lower() == "asc" else desc(colmap[order_by])

    where_clauses = []
    params = {}
    if filters:
        for k, v in filters.items():
            if k not in colmap:
                raise ValidationFailed("unknown filter", {"field": k})
            where_clauses.append(colmap[k] == v)   # safe bind, no SQL injection
            params[k] = v

    stmt = select(table)
    if where_clauses:
        from sqlalchemy import and_
        stmt = stmt.where(and_(*where_clauses))
    if order_clause is not None:
        stmt = stmt.order_by(order_clause)
    stmt = stmt.limit(limit).offset(offset)

    with session_scope() as s:
        rows = s.execute(stmt).mappings().all()
        return {
            "count": len(rows),
            "items": [dict(r) for r in rows]
            }