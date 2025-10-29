from __future__ import annotations
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Path, Query, Depends, Request, Body

from app.auth import require_auth
from . import repo


# ----- Request models -----

def build_generic_router(contract_store) -> APIRouter:
    """
    Returns a composed router that includes:
      - /tables/... endpoints (schema, list, insert, batch)
    The contract_store is injected from app.main to avoid circular imports.
    """

    tables_router = APIRouter(
        prefix="/tables",
        tags=["generic"],
        dependencies=[Depends(require_auth)],
    )

   # Map repo exceptions to HTTP responses (DRY)
    def handle_repo_exceptions(e: Exception):
        if isinstance(e, repo.NotAllowed):
            raise HTTPException(status_code=404, detail=str(e))
        if isinstance(e, repo.ValidationFailed):
            raise HTTPException(status_code=400, detail=e.payload or str(e))
        if isinstance(e, repo.DbConstraintError):
            raise HTTPException(status_code=400, detail={"db_error": "integrity_error", **(e.payload or {})})
        if isinstance(e, repo.DbSqlError):
            raise HTTPException(status_code=400, detail={"db_error": "sql_error", **(e.payload or {})})
        # unknown exception -> re-raise
        raise e
    
    
    # Returns the JSON contract/schema for the resource from contract_store.
    @tables_router.get("/{resource}/schema")
    def get_schema(resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$")):
        try:
            schema = contract_store.get(resource)
            if not schema:
                raise repo.NotAllowed(f"Table '{resource}' not found")
            return schema
        except Exception as e:
            handle_repo_exceptions(e)

    # List rows from the DB for the specified resource. Supports filters, ordering, pagination.
    @tables_router.get("/{resource}")
    def list_rows(
        resource: str,
        request: Request,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
        order_by: Optional[str] = Query(None),
        order_dir: str = Query("desc", pattern="^(?i:asc|desc)$")
    ):
        try:
            # Extract user filters from query parameters (exclude pagination/order params).
            filters = {
                k: v for k, v in request.query_params.items()
                if k not in {"limit", "offset", "order_by", "order_dir"}
            }
            return repo.list_rows(
                resource=resource,
                limit=limit,
                offset=offset,
                order_by=order_by,
                order_dir=order_dir,
                filters=filters or None,
            )
        except Exception as e:
            handle_repo_exceptions(e)

    # Insert a single row into the resource after validation.
    @tables_router.post("/{resource}", status_code=201)
    def create_row(
        resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"),
        body: Dict[str, Any] = Body(...),
        returning: str = Query("keys", enum=["keys", "full"]),
    ):
        try:
            return repo.insert_row(resource, body, returning)
        except Exception as e:
           handle_repo_exceptions(e)

    # Insert multiple rows (batch) into the resource, validating each entry.
    @tables_router.post("/{resource}/rows:batch")
    def create_rows_batch(
        resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"),
        body: List[Dict[str, Any]] = Body(...),
    ):
        try:
            return repo.insert_batch(resource, body)
        except Exception as e:
            handle_repo_exceptions(e)

    # Partial update (PATCH): body must include {"keys": {...}, "data": {...}}
    @tables_router.patch("/{resource}/rows")
    def patch_row(
        resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"),
        body: Dict[str, Any] = Body(...),
    ):
        try:
            keys = body.get("keys")
            data = body.get("data")
            if not isinstance(keys, dict) or not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="body must include 'keys' and 'data' objects")
            return repo.update_row(resource, keys, data, replace=False)
        except Exception as e:
            handle_repo_exceptions(e)

    # Full replace (PUT): body must include {"keys": {...}, "data": {...}} and does full validation
    @tables_router.put("/{resource}/rows")
    def put_row(
        resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"),
        body: Dict[str, Any] = Body(...),
    ):
        try:
            keys = body.get("keys")
            data = body.get("data")
            if not isinstance(keys, dict) or not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="body must include 'keys' and 'data' objects")
            return repo.update_row(resource, keys, data, replace=True)
        except Exception as e:
            handle_repo_exceptions(e)

    # Delete row
    @tables_router.delete("/{resource}/rows")
    def delete_row(
        resource: str = Path(..., pattern=r"^[a-zA-Z_][a-zA-Z0-9_]*$"),
        body: Dict[str, Any] = Body(...),
    ):
        try:
            keys = body.get("keys")
            if not isinstance(keys, dict):
                raise HTTPException(status_code=400, detail="body must include 'keys' object")
            return repo.delete_row(resource, keys)
        except Exception as e:
            handle_repo_exceptions(e)

            
    return tables_router
