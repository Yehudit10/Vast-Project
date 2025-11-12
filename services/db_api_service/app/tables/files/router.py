# app/tables/files/router.py
from typing import Optional, Any, Dict
from urllib.parse import unquote, quote
import os, json

from fastapi import APIRouter, HTTPException, Query
from .schemas import FilesCreate, FilesUpdate
from . import repo

router = APIRouter(prefix="/files", tags=["files"])
PUBLIC_S3_BASE = os.getenv("PUBLIC_S3_BASE")


def _attach_url_if_possible(row: Dict[str, Any]) -> Dict[str, Any]:
    if not row:
        return row
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


# @router.get("/", summary="List all files")
# def list_files(
#     bucket: Optional[str] = None,
#     device_id: Optional[str] = None,
#     limit: int = Query(50, ge=1, le=500),
# ):
#     if bucket is not None:
#         bucket = unquote(bucket)
#     rows = repo.list_files(bucket, device_id, limit)
#     return [_attach_url_if_possible(r) for r in rows]

@router.get("/", summary="List all file aggregates with filters")
def list_file_aggregates(
    run_id: Optional[str] = None,
    type: Optional[str] = Query(None, description="Predicted label (noise type)"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by filename"),
    sort_by: Optional[str] = Query("processing_ms", description="Sort field"),
    order: Optional[str] = Query("desc", description="Sort order: asc or desc"),
    limit: int = Query(50, ge=1, le=500),
):
    PUBLIC_S3_BASE = os.getenv("PUBLIC_S3_BASE", "http://minio:9000")

    conditions = []
    params = {}

    if run_id:
        conditions.append("fa.run_id = :run_id")
        params["run_id"] = run_id
    if type and type.lower() != "all types" and type.lower() != "all signals":
        conditions.append("fa.head_pred_label ILIKE :type")
        params["type"] = f"%{type}%"
    if search:
        conditions.append("f.path ILIKE :search")
        params["search"] = f"%{search}%"

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    sort_map = {

        "Length": "f.duration_s DESC",
        "processing_ms": "fa.processing_ms DESC",
        "filename": "f.path ASC",
    }
    order_clause = sort_map.get(sort_by, "fa.processing_ms DESC")

    # ✅ הסר bucket ו-object_key שלא קיימים בטבלה
    query = f"""
    SELECT 
        f.file_id,
        f.path AS filename,
        f.duration_s,
        f.sample_rate,
        f.size_bytes,
        fa.run_id,
        fa.head_pred_label,
        fa.head_pred_prob,
        fa.processing_ms,
        fa.num_windows,
        fa.agg_mode
    FROM agcloud_audio.file_aggregates fa
    JOIN agcloud_audio.files f ON fa.file_id = f.file_id
    {where_clause}
    ORDER BY {order_clause}
    LIMIT :limit;
    """
    params["limit"] = limit

    try:
        rows = repo.db_query(query, params)

        results = []
        for r in rows:
            filename = r.get("filename")
            url = f"{PUBLIC_S3_BASE.rstrip('/')}/hot/{filename}" if filename else None

            results.append({
                "filename": filename,
                "predicted_label": r.get("head_pred_label"),
                "probability": r.get("head_pred_prob"),
                "processing_ms": r.get("processing_ms"),
                "num_windows": r.get("num_windows"),
                "agg_mode": r.get("agg_mode"),
                "duration_s": r.get("duration_s"),
                "run_id": r.get("run_id"),
                "file_id": r.get("file_id"),
                "url": url
            })
        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.get("/{file_id:int}", summary="Get file by ID")
def get_file_by_id(file_id: int):
    row = repo.get_file_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return _attach_url_if_possible(row)


@router.get("/{bucket}", summary="List files in bucket")
def list_files_in_bucket(
    bucket: str,
    device_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    bucket = unquote(bucket)
    rows = repo.list_files(bucket, device_id, limit)
    return [_attach_url_if_possible(r) for r in rows]


@router.get("/{bucket}/{object_key:path}", summary="Get file by bucket/key")
def get_file(bucket: str, object_key: str):
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    row = repo.get_file(bucket, object_key)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return _attach_url_if_possible(row)


@router.put("/{bucket}/{object_key:path}", summary="Update file metadata")
def update_file(bucket: str, object_key: str, payload: FilesUpdate):
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    ok = repo.update_file(bucket, object_key, payload.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "ok"}


@router.delete("/{bucket}/{object_key:path}", summary="Delete file")
def delete_file(bucket: str, object_key: str):
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    ok = repo.delete_file(bucket, object_key)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "deleted"}
