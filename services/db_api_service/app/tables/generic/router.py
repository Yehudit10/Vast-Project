# app/tables/generic/router.py
# Handles HTTP requests: parses input, calls repo functions, maps repo errors to HTTP responses.

from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, Depends, Request
from pydantic import BaseModel

from app.auth import require_auth
from . import repo

router = APIRouter(prefix="/tables", tags=["generic"])

# Pydantic model for a single insert request.
class InsertRequest(BaseModel):
    data: Dict[str, Any]

# Pydantic model for a batch insert request.
class InsertBatchRequest(BaseModel):
    data: List[Dict[str, Any]]

# Returns the schema (columns and types) for a given table.
@router.get("/{resource}/schema")
def get_schema(resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"),
               _auth=Depends(require_auth)):
    """
    Returns the schema (column names, types, etc.) for the specified table.
    """
    try:
        return repo.describe_table(resource)
    except repo.NotAllowed as e:
        raise HTTPException(status_code=404, detail=str(e))

# Lists rows from the specified table, supports filtering, ordering, and pagination.
@router.get("/{resource}/rows")
def list_rows(
    resource: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    order_by: Optional[str] = Query(None),
    order_dir: str = Query("desc", pattern="^(?i)(asc|desc)$"),
    _auth=Depends(require_auth),
):
    """
    Returns a list of rows from the specified table, with optional filtering, ordering, and pagination.
    """
    filters = {k: v for k, v in request.query_params.items()
               if k not in {"limit", "offset", "order_by", "order_dir"}}

    try:
        return repo.list_rows(
            resource=resource,
            limit=limit,
            offset=offset,
            order_by=order_by,
            order_dir=order_dir,
            filters=filters or None,
        )
    except repo.NotAllowed as e:
        raise HTTPException(status_code=404, detail=str(e))
    except repo.ValidationFailed as e:
        raise HTTPException(status_code=400, detail=e.payload or str(e))
    except repo.DbSqlError as e:
        raise HTTPException(status_code=400, detail={"db_error": "sql_error", **(e.payload or {})})
    
# Inserts a single row into the specified table after validation.
@router.post("/{resource}/rows", status_code=201)
def create_row(resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"),
               body: InsertRequest = ...,
               returning: str = Query("keys", enum=["keys", "full"]),
               _auth=Depends(require_auth)):
    """
    Inserts a single row into the specified table after validating the input data.
    """
    try:
        return repo.insert_one(resource, body.data, returning)
    except repo.NotAllowed as e:
        raise HTTPException(status_code=404, detail=str(e))
    except repo.ValidationFailed as e:
        raise HTTPException(status_code=400, detail=e.payload or str(e))
    except repo.DbConstraintError as e:
        raise HTTPException(status_code=400, detail={"db_error": "integrity_error", **(e.payload or {})})
    except repo.DbSqlError as e:
        raise HTTPException(status_code=400, detail={"db_error": "sql_error", **(e.payload or {})})

# Inserts multiple rows (batch) into the specified table after validation.
@router.post("/{resource}/rows:batch")
def create_rows_batch(resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"),
                      body: InsertBatchRequest = ...,
                      _auth=Depends(require_auth)):
    """
    Inserts multiple rows (batch) into the specified table after validating the input data.
    """
    try:
        return repo.insert_batch(resource, body.data)
    except repo.NotAllowed as e:
        raise HTTPException(status_code=404, detail=str(e))
    except repo.ValidationFailed as e:
        raise HTTPException(status_code=400, detail=e.payload or str(e))
    except repo.DbConstraintError as e:
        raise HTTPException(status_code=400, detail={"db_error": "integrity_error", **(e.payload or {})})
    except repo.DbSqlError as e:
        raise HTTPException(status_code=400, detail={"db_error": "sql_error", **(e.payload or {})})
