from __future__ import annotations
# app/tables/generic/repo.py
# Schema-first repository: load JSON contracts, build in-memory SQLAlchemy Table,
# validate payloads, and perform read/insert operations (single + batch).
from typing import Any, Dict, List, Optional
from functools import lru_cache
import json
import os

from sqlalchemy import (
    Table,
    Column,
    MetaData,
    String,
    Integer,
    Boolean,
    Date,
    DateTime,
    Float,
    Numeric,
    insert,
    select,
    asc,
    desc,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from jsonschema import Draft202012Validator, ValidationError as JsonSchemaValidationError

from app.db import session_scope
from app.config import settings

ALLOWED_TABLES = set(settings.ALLOWED_TABLES)
CONTRACTS_DIR = settings.CONTRACTS_DIR

# -------------------- Exceptions (repo-level) -------------------- #
class RepoError(Exception):
    """Base repo error carrying optional payload for HTTP layer."""
    def __init__(self, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.payload = payload or {}

class NotAllowed(RepoError):
    """Raised when a requested resource/table is not allowed or not found."""
    pass

class ValidationFailed(RepoError):
    """Raised when input validation against the JSON contract fails."""
    pass

class DbConstraintError(RepoError):
    """Raised on DB integrity/constraint errors (e.g. unique violation)."""
    pass

class DbSqlError(RepoError):
    """Raised on general SQL/database errors."""
    pass

# -------------------- Contract loading / table build -------------------- #

@lru_cache(maxsize=256)
def _load_contract(resource: str) -> Dict[str, Any]:
    """
    Load and return the JSON contract for `resource` from CONTRACTS_DIR.
    Raises NotAllowed if resource is not allowed or file missing.
    Raises ValidationFailed if the JSON is invalid.
    """
    if resource not in ALLOWED_TABLES:
        raise NotAllowed(f"Table '{resource}' not allowed")
    path = os.path.join(CONTRACTS_DIR, f"{resource}.json")
    if not os.path.isfile(path):
        raise NotAllowed(f"Contract for '{resource}' not found at {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        raise ValidationFailed("invalid contract JSON", {"detail": str(e)})

@lru_cache(maxsize=256)
def _build_table_from_contract(resource: str) -> Table:
    """
    Build an in-memory SQLAlchemy Table object from the JSON contract.
    This table is used only for SQL generation (no reflection).
    """
    contract = _load_contract(resource)
    md = MetaData()
    props = contract.get("properties", {})
    cols: List[Column] = []
    for name, prop in props.items():
        coltype = _jsonschema_type_to_sqla(prop)
        # do not attempt to guess PK/autoincrement reliably from schema;
        # keep columns simple — DB defaults/autoincrement will still work.
        cols.append(Column(name, coltype, nullable=not prop.get("required", False)))
    return Table(resource, md, *cols)

# -------------------- JSON Schema -> SQLAlchemy type mapping -------------------- #
def _jsonschema_type_to_sqla(prop: dict) -> Any:
    """
    Map a JSON Schema property to a SQLAlchemy column type.
    Conservative defaults are used.
    """
    t = (prop.get("type") or "string").lower()
    fmt = (prop.get("format") or "").lower()

    if t == "integer":
        return Integer
    if t == "number":
        # prefer Numeric for exactness if format indicates decimal
        return Numeric if fmt in {"decimal", "numeric"} else Float
    if t == "boolean":
        return Boolean
    if t == "string":
        if fmt in {"date"}:
            return Date
        if fmt in {"date-time", "datetime"}:
            return DateTime
        if fmt in {"uuid"}:
            return String(36)
        # default string
        return String
    if t == "object" or t == "array":
        return JSONB
    # fallback
    return String

# -------------------- Validation helpers -------------------- #
def _validate_with_contract(resource: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the payload dict against the resource JSON contract using jsonschema.
    Returns the input payload (possibly cleaned) or raises ValidationFailed.
    """
    contract = _load_contract(resource)
    # The contract may be a full JSON Schema for an object.
    validator = Draft202012Validator(contract)
    try:
        validator.validate(payload)
        # return payload as-is; pydantic-type coercion is not applied here.
        return payload
    except JsonSchemaValidationError as e:
        # jsonschema exception doesn't provide a simple errors() like pydantic;
        # provide the message and path for debugging.
        raise ValidationFailed("validation error", {"detail": str(e), "path": list(e.path)})

def _validate(resource: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility wrapper used by router code."""
    return _validate_with_contract(resource, payload)

# -------------------- Public repo API -------------------- #
def describe_table(resource: str) -> Dict[str, Any]:
    """
    Return the JSON contract for the resource and a lightweight columns summary.
    Raises NotAllowed if missing.
    """
    contract = _load_contract(resource)
    # build a simple columns list from properties for convenience
    props = contract.get("properties", {})
    columns = []
    for name, p in props.items():
        columns.append({
            "name": name,
            "type": p.get("type"),
            "format": p.get("format"),
        })
    return {"table": resource, "contract": contract, "columns": columns}

def list_rows(
    resource: str,
    limit: int = 50,
    offset: int = 0,
    order_by: Optional[str] = None,
    order_dir: str = "desc",
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Select rows from the resource table.
    - Validates order_by against contract columns.
    - Accepts simple equality filters only (key=value).
    - Returns dict {rows: [...], count: n}
    Raises NotAllowed / ValidationFailed / DbSqlError
    """
    table = _build_table_from_contract(resource)
    allowed_cols = {c.name for c in table.columns}

    # validate order_by
    if order_by and order_by not in allowed_cols:
        raise ValidationFailed("invalid order_by", {"allowed": sorted(allowed_cols)})

    # build base select
    stmt = select(table).limit(limit).offset(offset)
    # ordering
    if order_by:
        col = table.c[order_by]
        stmt = stmt.order_by(asc(col) if order_dir.lower().startswith("asc") else desc(col))
    # filters (only allow known columns)
    if filters:
        for k, v in filters.items():
            if k not in allowed_cols:
                raise ValidationFailed("invalid filter key", {"key": k})
            stmt = stmt.where(table.c[k] == v)

    try:
        with session_scope() as s:
            res = s.execute(stmt)
            rows = [dict(r) for r in res.mappings().all()]
            return {"rows": rows, "count": len(rows)}
    except SQLAlchemyError as e:
        raise DbSqlError("sql error", {"detail": str(e)})

def insert_row(resource: str, payload: Dict[str, Any], returning: str = "keys") -> Dict[str, Any]:
    """
    Insert a single row into resource after validating against the contract.
    Returns {"affected_rows": 1, "returning": <row_dict> | None}.
    """
    table = _build_table_from_contract(resource)
    allowed_cols = {c.name for c in table.columns}

    unknown = set(payload) - allowed_cols
    if unknown:
        raise ValidationFailed("unknown fields", {"unknown_fields": sorted(unknown)})

    # validate payload
    try:
        valid = _validate_with_contract(resource, payload)
    except ValidationFailed as e:
        raise e

    stmt = insert(table).values(**valid).returning(*table.columns)
    try:
        with session_scope() as s:
            res = s.execute(stmt)
            row = res.mappings().first() if res.returns_rows else None
            return {"affected_rows": 1, "returning": dict(row) if row else None}
    except IntegrityError as e:
        raise DbConstraintError("integrity error", {"detail": str(e.orig)})
    except SQLAlchemyError as e:
        raise DbSqlError("sql error", {"detail": str(e)})

def insert_batch(resource: str, payloads: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Insert multiple rows in a single DB call where possible.
    Returns {"affected_rows": n}. Raises on validation/db errors.
    """
    if not payloads:
        return {"affected_rows": 0}

    table = _build_table_from_contract(resource)
    allowed_cols = {c.name for c in table.columns}

    to_insert: List[Dict[str, Any]] = []
    for p in payloads:
        unknown = set(p) - allowed_cols
        if unknown:
            raise ValidationFailed("unknown fields in batch", {"unknown_fields": sorted(unknown)})
        try:
            valid = _validate_with_contract(resource, p)
            to_insert.append(valid)
        except ValidationFailed as e:
            raise e

    try:
        with session_scope() as s:
            # use bulk insert using SQLAlchemy insert with multiple parameter sets
            s.execute(insert(table), to_insert)
            return {"affected_rows": len(to_insert)}
    except IntegrityError as e:
        raise DbConstraintError("integrity error", {"detail": str(e.orig)})
    except SQLAlchemyError as e:
        raise DbSqlError("sql error", {"detail": str(e)})
