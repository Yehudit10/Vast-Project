# app/tables/files/router.py
from typing import Optional, Any, Dict
from urllib.parse import unquote, quote
import os, json

from fastapi import APIRouter, HTTPException, Query
from .schemas import FilesCreate, FilesUpdate
from . import repo
import requests

router = APIRouter(prefix="/files", tags=["files"])
# PUBLIC_S3_BASE = os.getenv("PUBLIC_S3_BASE")
PUBLIC_S3_BASE = os.getenv("PUBLIC_S3_BASE", "http://localhost:9001")
MINIO_BASE = "http://minio-hot:9000"

def _check_if_compressed_in_minio(bucket: str, object_key: str) -> bool:
    """
    Check in MinIO if the file is compressed (OPUS format)
    Uses direct file path checking via MinIO container
    """
    try:
        # הסר .wav/.opus מהשם
        base_key = object_key.replace('.wav', '').replace('.opus', '')
        
        # נסה את כל האפשרויות
        possible_extensions = ['.opus', '.wav', '']
        
        print(f"[DEBUG] Checking MinIO for bucket={bucket}, base={base_key}")
        
        for ext in possible_extensions:
            test_key = f"{base_key}{ext}"
            
            # MinIO S3 API endpoint format
            url = f"{MINIO_BASE}/{bucket}/{test_key}"
            
            try:
                print(f"[DEBUG] HEAD request to: {url}")
                
                # נסה GET במקום HEAD (יותר אמין)
                response = requests.get(url, timeout=3, stream=True)
                
                if response.status_code == 200:
                    is_opus = test_key.lower().endswith('.opus')
                    print(f"[DEBUG] ✓ Found: {url} (OPUS={is_opus})")
                    response.close()
                    return is_opus
                elif response.status_code == 404:
                    print(f"[DEBUG] Not found (404): {url}")
                else:
                    print(f"[DEBUG] Status {response.status_code}: {url}")
                    
            except requests.exceptions.Timeout:
                print(f"[DEBUG] Timeout for: {url}")
                continue
            except requests.exceptions.ConnectionError as e:
                print(f"[DEBUG] Connection error for {url}: {e}")
                continue
            except Exception as e:
                print(f"[DEBUG] Error for {url}: {e}")
                continue
        
        print(f"[DEBUG] ✗ No file found for {bucket}/{object_key}")
        return False
        
    except Exception as e:
        print(f"[ERROR] MinIO check failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
def _attach_url_if_possible(row: Dict[str, Any]) -> Dict[str, Any]:
    """Attach a public URL to access the file from MinIO."""
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

    # Device filter
    if device_ids:
        device_list = [d.strip() for d in device_ids.split(",") if d.strip()]
        if device_list:
            placeholders = ", ".join([f":dev_{i}" for i in range(len(device_list))])
            conditions.append(f"(split_part(snsc.file_name, '_', 1)) IN ({placeholders})")
            for i, dev in enumerate(device_list):
                params[f"dev_{i}"] = dev

    # Date filters
    if date_from:
        conditions.append("COALESCE(sm.capture_time, snsc.linked_time) >= CAST(:date_from AS timestamptz)")
        params["date_from"] = date_from

    if date_to:
        conditions.append("COALESCE(sm.capture_time, snsc.linked_time) < CAST(:date_to AS timestamptz) + INTERVAL '1 day'")
        params["date_to"] = date_to

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Sorting options
    sort_map = {
        "Date (Newest)": "COALESCE(sm.capture_time, snsc.linked_time) DESC",
        "Date (Oldest)": "COALESCE(sm.capture_time, snsc.linked_time) ASC",
        "Length": "sm.duration_sec DESC",
        "Device": "snsc.file_name ASC",
        "processing_ms": "fa.processing_ms DESC",
        "filename": "snsc.file_name ASC",
    }
    order_clause = sort_map.get(sort_by, "COALESCE(sm.capture_time, snsc.linked_time) DESC")
        
    query = f"""
        SELECT
            fa.file_id,
            snsc.key AS combined_key,
            split_part(snsc.key, '/', 1) AS bucket,
            regexp_replace(snsc.key, '^[^/]+/', '') AS object_key,
            COALESCE(sm.file_name, snsc.file_name) AS filename,
            sm.device_id AS device_id,
            COALESCE(sm.capture_time, snsc.linked_time) AS capture_time,
            fa.head_pred_label,
            fa.head_pred_prob,
            fa.agg_mode,
            fa.num_windows
        FROM agcloud_audio.file_aggregates fa
        JOIN public.sound_new_sounds_connections snsc
            ON fa.file_id = snsc.id
        LEFT JOIN public.sounds_metadata sm
            ON sm.file_name = snsc.file_name
        {where_clause}
        ORDER BY {order_clause}
        LIMIT :limit;
    """

    params["limit"] = limit

    try:
        print("===== SQL QUERY =====")
        print(query)
        print("===== PARAMS =====")
        print(params)

        rows = repo.db_query(query, params)
        results = []

        for r in rows:
            bucket = r.get("bucket")
            object_key = r.get("object_key")
            filename = r.get("filename", "")
            
            url = None
            if bucket and object_key:
                url = f"{PUBLIC_S3_BASE.rstrip('/')}/{quote(bucket, safe='')}/{quote(object_key, safe='/')}"

            is_compressed = False
            if bucket and object_key:
                is_compressed = _check_if_compressed_in_minio(bucket, object_key)
                print(f"[DEBUG] File {filename}: is_compressed={is_compressed}")

            results.append({
                "file_id": r.get("file_id"),
                "filename": filename,
                "predicted_label": r.get("head_pred_label"),
                "probability": r.get("head_pred_prob"),
                "device_id": (filename or "").split("_")[0] if filename else "Unknown",
                "url": url,
                "is_compressed": is_compressed,  
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
    device_ids: Optional[str] = Query(None, description="Comma-separated device IDs"),
    sort_by: Optional[str] = Query("Date (Newest)", description="Sort field"),
    limit: int = Query(100, ge=1, le=500),
):
    conditions = []
    params: Dict[str, Any] = {}

    if predicted_class and predicted_class.lower() not in ("all signals", "all types"):
        conditions.append("upp.predicted_class ILIKE :pred_class")
        params["pred_class"] = f"%{predicted_class}%"

    if search:
        conditions.append("upp.file ILIKE :search")
        params["search"] = f"%{search}%"

    if date_from:
        conditions.append("upp.prediction_time >= CAST(:date_from AS timestamptz)")
        params["date_from"] = date_from
    if date_to:
        conditions.append("upp.prediction_time < CAST(:date_to AS timestamptz) + INTERVAL '1 day'")
        params["date_to"] = date_to

    where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

    sort_map = {
        "Date (Newest)": "upp.prediction_time DESC",
        "Date (Oldest)": "upp.prediction_time ASC",
        "filename": "upp.file ASC"
    }
    order_clause = sort_map.get(sort_by, "upp.prediction_time DESC")

    query = f"""
    SELECT 
        upp.id,
        upp.file,
        upp.predicted_class,
        upp.confidence,
        upp.watering_status,
        upp.status,
        snpc.key AS combined_key,
        split_part(snpc.key, '/', 1) AS bucket,
        regexp_replace(snpc.key, '^[^/]+/', '') AS object_key,
        COALESCE(sm.file_name, snpc.file_name) AS filename,
        COALESCE(sm.capture_time, snpc.linked_time) AS capture_time
    FROM public.ultrasonic_plant_predictions upp
    LEFT JOIN public.sound_new_plants_connections snpc
        ON snpc.file_name = upp.file
    LEFT JOIN public.sounds_metadata sm
        ON sm.file_name = snpc.file_name
    {where_clause}
    ORDER BY {order_clause}
    LIMIT :limit;
    """

    params["limit"] = limit

    try:
        rows = repo.db_query(query, params)
        results = []
        
        for r in rows:
            bucket = r.get("bucket")
            object_key = r.get("object_key")
            filename = r.get("file", "")
            
            url = None
            if bucket and object_key:
                url = f"{PUBLIC_S3_BASE.rstrip('/')}/{quote(bucket, safe='')}/{quote(object_key, safe='/')}"
            
            is_compressed = False
            if bucket and object_key:
                is_compressed = _check_if_compressed_in_minio(bucket, object_key)
            
            results.append({
                "id": r.get("id"),
                "file": filename,
                "predicted_class": r.get("predicted_class"),
                "confidence": r.get("confidence"),
                "watering_status": r.get("watering_status"),
                "status": r.get("status"),
                "device_id": ((filename or "").split("_")[0] or "Unknown"),
                "url": url,
                "is_compressed": is_compressed,
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
