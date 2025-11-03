# app/tables/files/router.py
from typing import Optional, Any, Dict
from urllib.parse import unquote, quote
import os
import json

from fastapi import APIRouter, HTTPException, Query
from .schemas import FilesCreate, FilesUpdate
from . import repo

router = APIRouter(prefix="/files", tags=["files"])

PUBLIC_S3_BASE = os.getenv("PUBLIC_S3_BASE")  # e.g., "http://minio:9000" or "https://cdn.example.com"


def _attach_url_if_possible(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    If metadata has 'url' or 's3_url', expose it as 'url'.
    Else, if PUBLIC_S3_BASE is set and we have bucket/key, build a path-style URL.
    """
    if not row:
        return row

    # Try metadata first
    meta = row.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = None

    if isinstance(meta, dict):
        for k in ("url", "s3_url"):
            if meta.get(k):
                row.setdefault("url", meta[k])
                return row

    # Build from PUBLIC_S3_BASE, if available
    if PUBLIC_S3_BASE and row.get("bucket") and (row.get("key") or row.get("object_key")):
        bucket = str(row["bucket"])
        key = str(row.get("key") or row.get("object_key"))
        built = f"{PUBLIC_S3_BASE.rstrip('/')}/{quote(bucket, safe='')}/{quote(key, safe='/')}"
        row.setdefault("url", built)

    return row


@router.post("", status_code=201)
def create_or_upsert_file(payload: FilesCreate):
    repo.upsert_file(payload.model_dump(by_alias=True))
    return {"status": "ok"}


# -------- New: GET /files/{file_id} by numeric id (place this before the catch-all path route) --------
@router.get("/{file_id:int}")
def get_file_by_id(file_id: int):
    row = repo.get_file_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return _attach_url_if_possible(row)


@router.put("/{bucket}/{object_key:path}")
def update_file(bucket: str, object_key: str, payload: FilesUpdate):
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    ok = repo.update_file(bucket, object_key, payload.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "ok"}


@router.get("/{bucket}/{object_key:path}")
def get_file(bucket: str, object_key: str):
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    row = repo.get_file(bucket, object_key)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return _attach_url_if_possible(row)


@router.get("")
def list_files(
    bucket: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    if bucket is not None:
        bucket = unquote(bucket)
    rows = repo.list_files(bucket, device_id, limit)
    # Optionally attach URL to each row (cheap for small lists)
    return [_attach_url_if_possible(r) for r in rows]


@router.delete("/{bucket}/{object_key:path}")
def delete_file(bucket: str, object_key: str):
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    ok = repo.delete_file(bucket, object_key)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "deleted"}
