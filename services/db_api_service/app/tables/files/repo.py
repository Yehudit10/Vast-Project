# app/tables/files/repo.py
import os
import json
import time
import pathlib
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from app.db import session_scope

DRY_RUN = os.getenv("DB_DRY_RUN", "0") == "1"
SPOOL_DIR = os.getenv("DRY_RUN_SPOOL", "/tmp/api_spool")


def _spool(name: str, payload: Dict[str, Any]):
    p = pathlib.Path(SPOOL_DIR)
    p.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    (p / f"{ts}-{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _ensure_json_text(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)
    return obj


def upsert_file(payload: Dict[str, Any]) -> None:
    if DRY_RUN:
        _spool("files_upsert", payload)
        return

    payload = dict(payload)
    payload["metadata"] = _ensure_json_text(payload.get("metadata"))

    # optional footprint (WKT) -> geometry
    fp = payload.get("footprint")
    payload["footprint"] = (None if not fp else fp)

    q = text("""
        INSERT INTO files (
            bucket, object_key, content_type, size_bytes, etag,
            mission_id, device_id, tile_id, footprint, metadata
        )
        VALUES (
            :bucket, :object_key, :content_type, :size_bytes, :etag,
            :mission_id, :device_id, :tile_id,
            CASE
                WHEN NULLIF(CAST(:footprint AS text), '') IS NULL THEN NULL::geometry
                ELSE ST_GeomFromText(CAST(:footprint AS text), 4326)
            END,
            CAST(:metadata AS JSONB)
        )
        ON CONFLICT (bucket, object_key)
        DO UPDATE SET
            content_type = EXCLUDED.content_type,
            size_bytes   = EXCLUDED.size_bytes,
            etag         = EXCLUDED.etag,
            mission_id   = EXCLUDED.mission_id,
            device_id    = EXCLUDED.device_id,
            tile_id      = EXCLUDED.tile_id,
            footprint    = EXCLUDED.footprint,
            metadata     = EXCLUDED.metadata;
    """)
    with session_scope() as s:
        s.execute(q, payload)


def update_file(bucket: str, object_key: str, updates: Dict[str, Any]) -> bool:
    if DRY_RUN:
        _spool("files_update", {"bucket": bucket, "object_key": object_key, **updates})
        return True

    sets: List[str] = []
    params: Dict[str, Any] = {"bucket": bucket, "object_key": object_key}

    if "content_type" in updates and updates["content_type"] is not None:
        sets.append("content_type=:content_type")
        params["content_type"] = updates["content_type"]

    if "size_bytes" in updates and updates["size_bytes"] is not None:
        sets.append("size_bytes=:size_bytes")
        params["size_bytes"] = updates["size_bytes"]

    if "etag" in updates and updates["etag"] is not None:
        sets.append("etag=:etag")
        params["etag"] = updates["etag"]

    if "mission_id" in updates and updates["mission_id"] is not None:
        sets.append("mission_id=:mission_id")
        params["mission_id"] = updates["mission_id"]

    if "device_id" in updates and updates["device_id"] is not None:
        sets.append("device_id=:device_id")
        params["device_id"] = updates["device_id"]

    if "tile_id" in updates and updates["tile_id"] is not None:
        sets.append("tile_id=:tile_id")
        params["tile_id"] = updates["tile_id"]

    if "footprint" in updates:
        fp = updates["footprint"]
        params["footprint"] = (None if not fp else fp)
        sets.append(
            "footprint = CASE "
            "WHEN NULLIF(CAST(:footprint AS text), '') IS NULL THEN NULL::geometry "
            "ELSE ST_GeomFromText(CAST(:footprint AS text), 4326) "
            "END"
        )

    if "metadata" in updates and updates["metadata"] is not None:
        params["metadata"] = _ensure_json_text(updates["metadata"])
        sets.append("metadata=CAST(:metadata AS JSONB)")

    if not sets:
        return True

    q = text(f"""
        UPDATE files
        SET {', '.join(sets)}
        WHERE bucket=:bucket AND object_key=:object_key
        RETURNING file_id;
    """)
    with session_scope() as s:
        row = s.execute(q, params).first()
        return bool(row)


def get_file(bucket: str, object_key: str) -> Optional[Dict[str, Any]]:
    if DRY_RUN:
        return None

    q = text("""
        SELECT
            file_id, bucket, object_key,
            object_key AS key,                       -- convenient alias
            content_type, size_bytes, etag,
            mission_id, device_id, tile_id,
            ST_AsText(footprint) AS footprint_wkt,
            metadata, created_at
        FROM files
        WHERE bucket=:bucket AND object_key=:object_key
        LIMIT 1;
    """)
    with session_scope() as s:
        row = s.execute(q, {"bucket": bucket, "object_key": object_key}).mappings().first()
        return dict(row) if row else None


def get_file_by_id(file_id: int) -> Optional[Dict[str, Any]]:
    """New: fetch by numeric file_id."""
    if DRY_RUN:
        return None

    q = text("""
        SELECT
            file_id, bucket, object_key,
            object_key AS key,                       -- convenient alias
            content_type, size_bytes, etag,
            mission_id, device_id, tile_id,
            ST_AsText(footprint) AS footprint_wkt,
            metadata, created_at
        FROM files
        WHERE file_id = :file_id
        LIMIT 1;
    """)
    with session_scope() as s:
        row = s.execute(q, {"file_id": file_id}).mappings().first()
        return dict(row) if row else None


def list_files(bucket: Optional[str], device_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
    if DRY_RUN:
        return []

    filters: List[str] = []
    params: Dict[str, Any] = {"limit": limit}

    if bucket:
        filters.append("bucket=:bucket")
        params["bucket"] = bucket

    if device_id:
        filters.append("device_id=:device_id")
        params["device_id"] = device_id

    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    q = text(f"""
        SELECT
            file_id, bucket, object_key,
            object_key AS key,                       -- convenient alias
            content_type, size_bytes, etag,
            mission_id, device_id, tile_id,
            ST_AsText(footprint) AS footprint_wkt,
            metadata, created_at
        FROM files
        {where}
        ORDER BY created_at DESC
        LIMIT :limit;
    """)
    with session_scope() as s:
        rows = s.execute(q, params).mappings().all()
        return [dict(r) for r in rows]


def delete_file(bucket: str, object_key: str) -> bool:
    if DRY_RUN:
        _spool("files_delete", {"bucket": bucket, "object_key": object_key})
        return True

    q = text("""
        DELETE FROM files
        WHERE bucket=:bucket AND object_key=:object_key
        RETURNING file_id;
    """)
    with session_scope() as s:
        row = s.execute(q, {"bucket": bucket, "object_key": object_key}).first()
        return bool(row)
