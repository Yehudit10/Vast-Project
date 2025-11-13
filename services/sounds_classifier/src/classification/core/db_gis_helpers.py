# db_gis_helpers.py
from __future__ import annotations
from typing import Optional, Tuple
from datetime import datetime, timezone

def _to_dt_utc(value):
    """Accepts datetime or ISO string (possibly ending with 'Z') and returns aware datetime in UTC."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = str(value)
    if s.endswith("Z"):
        s = s[:-1]  # drop Z for strptime
        dt = datetime.fromisoformat(s) if "T" in s else datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)
    try:
        # try full ISO first
        dt = datetime.fromisoformat(s)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        # last resort: YYYY-MM-DDTHH:MM:SS
        dt = datetime.strptime(s.replace(" ", "T"), "%Y-%m-%dT%H:%M:%S")
        return dt.replace(tzinfo=timezone.utc)

def fetch_gis_by_device_and_time(conn, device_id: str, started_at) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    started_dt = _to_dt_utc(started_at)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (gis_origin->>'latitude')::double precision  AS lat,
                  (gis_origin->>'longitude')::double precision AS lon,
                  (gis_origin->>'area')                        AS area
                FROM public.sounds_metadata
                WHERE device_id = %s
                  AND capture_time = %s
                LIMIT 1
                """,
                (device_id, started_dt),
            )
            row = cur.fetchone()
            if row:
                return row[0], row[1], row[2]

            cur.execute(
                """
                SELECT
                  (gis_origin->>'latitude')::double precision  AS lat,
                  (gis_origin->>'longitude')::double precision AS lon,
                  (gis_origin->>'area')                        AS area
                FROM public.sounds_metadata
                WHERE device_id = %s
                  AND capture_time BETWEEN %s - interval '30 seconds' AND %s + interval '30 seconds'
                ORDER BY ABS(EXTRACT(EPOCH FROM (capture_time - %s))) ASC
                LIMIT 1
                """,
                (device_id, started_dt, started_dt, started_dt),
            )
            row = cur.fetchone()
            if row:
                return row[0], row[1], row[2]
    except Exception:
        pass
    return None, None, None

def fetch_gis_by_filename(conn, file_name: str) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (gis_origin->>'latitude')::double precision  AS lat,
                  (gis_origin->>'longitude')::double precision AS lon,
                  (gis_origin->>'area')                        AS area
                FROM public.sounds_metadata
                WHERE file_name = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (file_name,),
            )
            row = cur.fetchone()
            if row:
                return row[0], row[1], row[2]
    except Exception:
        pass
    return None, None, None
