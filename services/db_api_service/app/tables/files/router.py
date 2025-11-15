
from typing import Optional, Any, Dict
from urllib.parse import unquote, quote
import os, json

from fastapi import APIRouter, HTTPException, Query
from .schemas import FilesCreate, FilesUpdate
from . import repo

router = APIRouter(prefix="/files", tags=["files"])

# MinIO endpoint - adjust based on your docker-compose
# From docker-compose: minio-hot is on port 9001 externally
PUBLIC_S3_BASE = os.getenv("PUBLIC_S3_BASE", "http://localhost:9002")


def _attach_url_if_possible(row: Dict[str, Any]) -> Dict[str, Any]:
    """Attach a public URL to access the file from MinIO"""
    if not row:
        return row
    
    # Try to extract URL from metadata first
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
    
    # Build URL from bucket + key
    bucket = row.get("bucket")
    key = row.get("key") or row.get("object_key")
    
    if PUBLIC_S3_BASE and bucket and key:
        bucket_str = str(bucket)
        key_str = str(key)
        # MinIO URL format: http://host:port/bucket/path/to/file
        built = f"{PUBLIC_S3_BASE.rstrip('/')}/{quote(key_str, safe='/')}"
        # built = f"{PUBLIC_S3_BASE.rstrip('/')}/{quote(bucket_str, safe='')}/{quote(key_str, safe='/')}"
        row.setdefault("url", built)
    
    return row

def _is_compressed(filename: str) -> bool:
    """Check if file is compressed (OPUS format)"""
    if not filename:
        return False
    return filename.lower().endswith('.opus')


@router.post("", status_code=201)
def create_or_upsert_file(payload: FilesCreate):
    """Create or update a file record"""
    repo.upsert_file(payload.model_dump(by_alias=True))
    return {"status": "ok"}

@router.get("/audio-aggregates/", summary="List audio file aggregates (environment sounds)")
def list_audio_aggregates(
    run_id: Optional[str] = None,
    type: Optional[str] = Query(None, description="Predicted label (noise type)"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by filename"),
    device_ids: Optional[str] = Query(None, description="Comma-separated device IDs"),
    sort_by: Optional[str] = Query("Date (Newest)", description="Sort field"),
    limit: int = Query(100, ge=1, le=500),
):
    conditions = []
    params: Dict[str, Any] = {}

    # Run filter
    if run_id:
        conditions.append("fa.run_id = :run_id")
        params["run_id"] = run_id

    # Label filter
    if type and type.lower() not in ("all types", "all signals"):
        conditions.append("fa.head_pred_label ILIKE :type")
        params["type"] = f"%{type}%"

    # Search filter on filename
    if search:
        conditions.append("snsc.file_name ILIKE :search")
        params["search"] = f"%{search}%"

    # Device filter (based on snsc.file_name prefix)
    if device_ids:
        device_list = [d.strip() for d in device_ids.split(",") if d.strip()]
        if device_list:
            placeholders = ", ".join([f":dev_{i}" for i in range(len(device_list))])
            conditions.append(f"(split_part(snsc.file_name, '_', 1)) IN ({placeholders})")
            for i, dev in enumerate(device_list):
                params[f"dev_{i}"] = dev

    # Date filters (based on public.files.created_at)
    if date_from:
        conditions.append("f.created_at >= CAST(:date_from AS timestamptz)")
        params["date_from"] = date_from

    if date_to:
        conditions.append("f.created_at < CAST(:date_to AS timestamptz) + INTERVAL '1 day'")
        params["date_to"] = date_to

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Sorting options
    sort_map = {
        "Date (Newest)": "f.created_at DESC",
        "Date (Oldest)": "f.created_at ASC",
        "Length": "f.size_bytes DESC",
        "Device": "snsc.file_name ASC",
        "processing_ms": "fa.processing_ms DESC",
        "filename": "snsc.file_name ASC",
    }
    order_clause = sort_map.get(sort_by, "f.created_at DESC")

    query = f"""
    SELECT
        fa.file_id,
        f.bucket,
        f.object_key,
        snsc.file_name AS filename,
        fa.head_pred_label,
        fa.head_pred_prob,
        f.created_at,
        f.content_type
    FROM agcloud_audio.file_aggregates fa
    JOIN public.sound_new_sounds_connections snsc 
        ON fa.file_id = snsc.id
    JOIN public.files f
        ON f.object_key LIKE '%' || snsc.key
    {where_clause}
    ORDER BY {order_clause}
    LIMIT :limit;
    """

    params["limit"] = limit

    try:
        rows = repo.db_query(query, params)
        results = []

        for r in rows:
            url = None
            if r.get("bucket") and r.get("object_key"):
                url = (
                    f"{PUBLIC_S3_BASE.rstrip('/')}/"
                    f"{quote(str(r['bucket']), safe='')}/"
                    f"{quote(str(r['object_key']), safe='/')}"
                )

            results.append({
                "file_id": r.get("file_id"),
                "filename": r.get("filename"),
                "predicted_label": r.get("head_pred_label"),
                "probability": r.get("head_pred_prob"),
                "device_id": (r.get("filename") or "").split("_")[0],
                "url": url,
            })

        return results

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("/plant-predictions/", summary="List ultrasonic plant predictions")
def list_plant_predictions(
    predicted_class: Optional[str] = Query(None, description="Filter by predicted class"),
    date_from: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    search: Optional[str] = Query(None, description="Search by filename"),
    device_ids: Optional[str] = Query(None, description="Comma-separated device IDs (if applicable)"),
    sort_by: Optional[str] = Query("Date (Newest)", description="Sort field"),
    limit: int = Query(100, ge=1, le=500),
):
    """
    Returns ultrasonic plant predictions from public.ultrasonic_plant_predictions
    
    This endpoint serves plant stress/watering sounds (Tomato Cut, Tobacco Dry, etc.)
    """
    conditions = []
    params: Dict[str, Any] = {}

    # Filter by predicted class
    if predicted_class and predicted_class.lower() not in ("all signals", "all types"):
        conditions.append("upp.predicted_class ILIKE :pred_class")
        params["pred_class"] = f"%{predicted_class}%"

    # Search by filename
    if search:
        conditions.append("upp.file ILIKE :search")
        params["search"] = f"%{search}%"

    # Date filters
    if date_from:
        conditions.append("upp.prediction_time >= CAST(:date_from AS timestamptz)")
        params["date_from"] = date_from
    if date_to:
        conditions.append("upp.prediction_time < CAST(:date_to AS timestamptz) + INTERVAL '1 day'")
        params["date_to"] = date_to

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Sort mapping
    sort_map = {
        "Date (Newest)": "upp.prediction_time DESC",
        "Date (Oldest)": "upp.prediction_time ASC",
        "filename": "upp.file ASC"
    }
    order_clause = sort_map.get(sort_by, "upp.prediction_time DESC")

    # Join with files table to get bucket/key for URL construction
    query = f"""
    SELECT 
        upp.id,
        upp.file,
        upp.predicted_class,
        upp.confidence,
        upp.watering_status,
        upp.status
    FROM public.ultrasonic_plant_predictions upp
    LEFT JOIN public.files f ON upp.id = f.file_id
    {where_clause}
    ORDER BY {order_clause}
    LIMIT :limit;
    """
    params["limit"] = limit

    try:
        rows = repo.db_query(query, params)
        results = []
        
        for r in rows:
            # Build MinIO URL
            url = None
            if r.get("bucket") and r.get("object_key"):
                bucket = str(r["bucket"])
                key = str(r["object_key"])
                url = f"{PUBLIC_S3_BASE.rstrip('/')}/{quote(bucket, safe='')}/{quote(key, safe='/')}"
            
            results.append({
                "id": r.get("id"),
                "file": r.get("file"),
                "predicted_class": r.get("predicted_class"),
                "confidence": r.get("confidence"),
                "watering_status": r.get("watering_status"),
                "status": r.get("status"),
                "device_id": ((r.get("file") or "").split("_")[0] or "Unknown"),
                "url": url
            })
        
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("/{file_id:int}", summary="Get file by ID")
def get_file_by_id(file_id: int):
    """Get a single file record by file_id"""
    row = repo.get_file_by_id(file_id)
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return _attach_url_if_possible(row)


@router.get("/{bucket}", summary="List files in bucket")
def list_files_in_bucket(
    bucket: str,
    device_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
):
    """List all files in a specific MinIO bucket"""
    bucket = unquote(bucket)
    rows = repo.list_files(bucket, device_id, limit)
    return [_attach_url_if_possible(r) for r in rows]


@router.get("/{bucket}/{object_key:path}", summary="Get file by bucket/key")
def get_file(bucket: str, object_key: str):
    """Get a file record by bucket and object_key"""
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    row = repo.get_file(bucket, object_key)
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    return _attach_url_if_possible(row)


@router.put("/{bucket}/{object_key:path}", summary="Update file metadata")
def update_file(bucket: str, object_key: str, payload: FilesUpdate):
    """Update file metadata"""
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    ok = repo.update_file(bucket, object_key, payload.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "ok"}


@router.delete("/{bucket}/{object_key:path}", summary="Delete file")
def delete_file(bucket: str, object_key: str):
    """Delete a file record (does not delete from MinIO)"""
    bucket = unquote(bucket)
    object_key = unquote(object_key)
    ok = repo.delete_file(bucket, object_key)
    if not ok:
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": "deleted"}