<<<<<<< HEAD
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from .schemas import FilesCreate, FilesUpdate
from . import repo

router = APIRouter(prefix="/files", tags=["files"])

@router.post("", status_code=201)
def create_or_upsert_file(payload: FilesCreate):
    repo.upsert_file(payload.model_dump(by_alias=True))
    return {"status": "ok"}

@router.put("/{bucket}/{object_key:path}")
def update_file(bucket: str, object_key: str, payload: FilesUpdate):
    ok = repo.update_file(bucket, object_key, payload.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "ok"}


@router.get("/{bucket}/{object_key:path}")
def get_file(bucket: str, object_key: str):
    row = repo.get_file(bucket, object_key)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row

@router.get("")
def list_files(bucket: Optional[str] = None,
               device_id: Optional[str] = None,
               limit: int = Query(50, ge=1, le=500)):
    return repo.list_files(bucket, device_id, limit)

@router.delete("/{bucket}/{object_key:path}")
def delete_file(bucket: str, object_key: str):
    ok = repo.delete_file(bucket, object_key)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "deleted"}
=======
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query
from .schemas import FilesCreate, FilesUpdate
from . import repo

router = APIRouter(prefix="/files", tags=["files"])

@router.post("", status_code=201)
def create_or_upsert_file(payload: FilesCreate):
    repo.upsert_file(payload.model_dump(by_alias=True))
    return {"status": "ok"}

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
    return row

@router.get("")
def list_files(
    bucket: Optional[str] = None,
    device_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
  
    if bucket is not None:
        bucket = unquote(bucket)
    return repo.list_files(bucket, device_id, limit)

@router.delete("/{bucket}/{object_key:path}")
def delete_file(bucket: str, object_key: str):
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    ok = repo.delete_file(bucket, object_key)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "deleted"}
>>>>>>> 2ab8ea6 (Add tests)
