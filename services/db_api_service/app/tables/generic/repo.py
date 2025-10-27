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
    update,
    delete,
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

_CONTRACT_STORE: Optional[Any] = None

def set_contract_store(store: Any) -> None:
    """
    Inject a ContractStore instance. After injection the repo will always
    read contracts from that store. Clears the _load_contract cache.
    """
    global _CONTRACT_STORE
    _CONTRACT_STORE = store
    # clear lru cache so previously cached file-based contracts (if any) do not linger
    try:
        _load_contract.cache_clear()
    except Exception:
        pass

@lru_cache(maxsize=256)
def _load_contract(resource: str) -> Dict[str, Any]:
    """
    Load and return the JSON contract for `resource`.
    Always prefer the injected ContractStore. If no store was injected,
    raise NotAllowed to force explicit wiring (prevents silent file reads).
    """
    # require injected store
    if _CONTRACT_STORE is None:
        raise NotAllowed("no contract_store injected into repo; call set_contract_store(store) during startup")

    schema = _CONTRACT_STORE.get(resource)
    if not schema:
        raise NotAllowed(f"Contract for '{resource}' not found in injected contract_store")
    return schema

@lru_cache(maxsize=256)
def _build_table_from_contract(resource: str) -> Table:
    """
    Build an in-memory SQLAlchemy Table object from the JSON contract.
    This table is used only for SQL generation (no reflection).
    """
    contract = _load_contract(resource)
    md = MetaData()
    props = contract.get("properties", {})
    required_set = set(contract.get("required", []) or [])
    cols: List[Column] = []
    for name, prop in props.items():
        coltype = _jsonschema_type_to_sqla(prop)
        prop_nullable = prop.get("nullable")
        if prop_nullable is not None:
            nullable = bool(prop_nullable)
        else:
            is_required = (name in required_set) or bool(prop.get("required", False))
            nullable = not is_required
        cols.append(Column(name, coltype, nullable=nullable))
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

def _validate_partial_against_props(props: Dict[str, Any], payload: Dict[str, Any]) -> None:
    """
    Validate only the provided fields in payload using a temporary schema
    built from the contract properties for those fields.
    Raises ValidationFailed on error.
    """
    # build minimal schema for the provided keys
    subset_props = {k: props[k] for k in payload.keys() if k in props}
    schema = {"type": "object", "properties": subset_props}
    validator = Draft202012Validator(schema)
    try:
        validator.validate(payload)
    except JsonSchemaValidationError as e:
        raise ValidationFailed("validation error", {"detail": str(e), "path": list(e.path)})

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

    Note: 'count' is the number of rows returned in this page (i.e. len(rows)),
    not the total number of matching rows in the table. This avoids an extra
    COUNT(*) query and keeps the endpoint faster.
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
    # load contract first and use its properties to determine allowed fields
    contract = _load_contract(resource)
    props = contract.get("properties", {})
    allowed_cols = set(props.keys())

    unknown = set(payload) - allowed_cols
    if unknown:
        raise ValidationFailed("unknown fields", {"unknown_fields": sorted(unknown)})

    # validate payload against contract (may add defaults / coerce)
    try:
        valid = _validate_with_contract(resource, payload)
    except ValidationFailed as e:
        raise e

    # build SQLAlchemy table afterwards for SQL generation
    table = _build_table_from_contract(resource)

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

    # determine allowed columns from contract properties first
    contract = _load_contract(resource)
    props = contract.get("properties", {})
    allowed_cols = set(props.keys())
    table = _build_table_from_contract(resource)

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

def update_row(resource: str, keys: Dict[str, Any], payload: Dict[str, Any], replace: bool = False) -> Dict[str, Any]:
    """
    Update (partial or full) a row identified by keys.
    - keys: mapping of key-field -> value (must include contract x-keyFields)
    - payload: fields to update
    - replace: if True, expect full payload and validate against full contract (PUT semantics)
    Returns {"affected_rows": n, "returning": <row_dict> | None}
    """
    contract = _load_contract(resource)
    props = contract.get("properties", {})
    allowed_cols = set(props.keys())

    if not keys or not isinstance(keys, dict):
        raise ValidationFailed("missing keys", {"detail": "provide keys dict to identify the row"})

    # ensure key fields exist in contract (prefer x-keyFields if provided)
    key_fields = contract.get("x-keyFields") or []
    if not key_fields:
        # fallback: try "id" or first property
        if "id" in props:
            key_fields = ["id"]
        else:
            raise ValidationFailed("no key fields", {"detail": "contract has no x-keyFields and no id"})

    missing_keys = [k for k in key_fields if k not in keys]
    if missing_keys:
        raise ValidationFailed("missing key fields", {"missing": missing_keys})

    # check unknown fields in payload
    unknown = set(payload) - allowed_cols
    if unknown:
        raise ValidationFailed("unknown fields", {"unknown_fields": sorted(unknown)})

    # validate payload:
    if replace:
        # full validation against contract (may enforce required)
        try:
            _validate_with_contract(resource, payload)
        except ValidationFailed as e:
            raise e
    else:
        # partial validation only for provided fields
        try:
            _validate_partial_against_props(props, payload)
        except ValidationFailed as e:
            raise e

    table = _build_table_from_contract(resource)

    # build where clause from key_fields
    where_clause = None
    for k in key_fields:
        cond = (table.c[k] == keys[k])
        where_clause = cond if where_clause is None else (where_clause & cond)

    stmt = update(table).where(where_clause).values(**payload).returning(*table.columns)
    try:
        with session_scope() as s:
            res = s.execute(stmt)
            row = res.mappings().first() if res.returns_rows else None
            affected = res.rowcount if hasattr(res, "rowcount") else (1 if row else 0)
            return {"affected_rows": int(affected), "returning": dict(row) if row else None}
    except IntegrityError as e:
        raise DbConstraintError("integrity error", {"detail": str(e.orig)})
    except SQLAlchemyError as e:
        raise DbSqlError("sql error", {"detail": str(e)})

def delete_row(resource: str, keys: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete a row identified by keys (contract x-keyFields required).
    Returns {"affected_rows": n}.
    """
    contract = _load_contract(resource)
    props = contract.get("properties", {})
    key_fields = contract.get("x-keyFields") or []
    if not key_fields:
        if "id" in props:
            key_fields = ["id"]
        else:
            raise ValidationFailed("no key fields", {"detail": "contract has no x-keyFields and no id"})

    missing_keys = [k for k in key_fields if k not in keys]
    if missing_keys:
        raise ValidationFailed("missing key fields", {"missing": missing_keys})

    table = _build_table_from_contract(resource)

    where_clause = None
    for k in key_fields:
        cond = (table.c[k] == keys[k])
        where_clause = cond if where_clause is None else (where_clause & cond)

    stmt = delete(table).where(where_clause)
    try:
        with session_scope() as s:
            res = s.execute(stmt)
            affected = res.rowcount if hasattr(res, "rowcount") else 0
            return {"affected_rows": int(affected)}
    except IntegrityError as e:
        raise DbConstraintError("integrity error", {"detail": str(e.orig)})
    except SQLAlchemyError as e:
        raise DbSqlError("sql error", {"detail": str(e)})
