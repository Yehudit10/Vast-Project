import os, json, time, pathlib
from typing import Any, Dict, List, Optional, Sequence
from sqlalchemy import text
from app.db import session_scope

DRY_RUN = os.getenv("DB_DRY_RUN", "0") == "1"
SPOOL_DIR = os.getenv("DRY_RUN_SPOOL", "/tmp/api_spool")

# ✅ Added ack to tracked fields
ALL_FIELDS = [
    "incident_id","mission_id","device_id","anomaly",
    "started_at","ended_at","duration_sec","frame_start","frame_end",
    "severity","is_real","ack",
    "roi_pixels","footprint","clip_file_id","poster_file_id","frames_manifest","meta",
]

def _normalize_incident_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(payload)
    for k in ALL_FIELDS:
        p.setdefault(k, None)
    p["roi_pixels"] = _ensure_json_text(p.get("roi_pixels"))
    p["frames_manifest"] = _ensure_json_text(p.get("frames_manifest"))
    p["meta"] = _ensure_json_text(p.get("meta"))
    return p

def _spool(name: str, payload: Any):
    p = pathlib.Path(SPOOL_DIR); p.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    (p / f"{ts}-{name}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

def _ensure_json_text(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, ensure_ascii=False)
    return obj

# ---------- Incidents ----------

def create_incident(payload: Dict[str, Any]) -> None:
    if DRY_RUN:
        _spool("incidents_insert", payload); return
    payload = _normalize_incident_payload(payload)
    q = text("""
        INSERT INTO incidents (
            incident_id, mission_id, device_id, anomaly,
            started_at, ended_at, duration_sec, frame_start, frame_end,
            severity, is_real, ack,
            roi_pixels, footprint, clip_file_id, poster_file_id, frames_manifest, meta
        )
        VALUES (
            :incident_id, :mission_id, :device_id, :anomaly,
            CAST(:started_at AS timestamptz),
            CAST(:ended_at AS timestamptz),
            :duration_sec, :frame_start, :frame_end,
            :severity, :is_real, :ack,
            CAST(:roi_pixels AS jsonb),
            CASE
              WHEN NULLIF(CAST(:footprint AS text), '') IS NULL THEN NULL::geometry
              ELSE ST_GeomFromText(CAST(:footprint AS text), 4326)
            END,
            :clip_file_id, :poster_file_id,
            CAST(:frames_manifest AS jsonb),
            CAST(:meta AS jsonb)
        );
    """)
    with session_scope() as s:
        s.execute(q, payload)

def upsert_incident(payload: Dict[str, Any]) -> None:
    if DRY_RUN:
        _spool("incidents_upsert", payload); return
    payload = _normalize_incident_payload(payload)
    q = text("""
        INSERT INTO incidents (
            incident_id, mission_id, device_id, anomaly,
            started_at, ended_at, duration_sec, frame_start, frame_end,
            severity, is_real, ack,
            roi_pixels, footprint, clip_file_id, poster_file_id, frames_manifest, meta
        )
        VALUES (
            :incident_id, :mission_id, :device_id, :anomaly,
            CAST(:started_at AS timestamptz),
            CAST(:ended_at AS timestamptz),
            :duration_sec, :frame_start, :frame_end,
            :severity, :is_real, :ack,
            CAST(:roi_pixels AS jsonb),
            CASE
              WHEN NULLIF(CAST(:footprint AS text), '') IS NULL THEN NULL::geometry
              ELSE ST_GeomFromText(CAST(:footprint AS text), 4326)
            END,
            :clip_file_id, :poster_file_id,
            CAST(:frames_manifest AS jsonb),
            CAST(:meta AS jsonb)
        )
        ON CONFLICT (incident_id) DO UPDATE SET
            mission_id      = EXCLUDED.mission_id,
            device_id       = EXCLUDED.device_id,
            anomaly         = EXCLUDED.anomaly,
            started_at      = EXCLUDED.started_at,
            ended_at        = EXCLUDED.ended_at,
            duration_sec    = EXCLUDED.duration_sec,
            frame_start     = EXCLUDED.frame_start,
            frame_end       = EXCLUDED.frame_end,
            severity        = EXCLUDED.severity,
            is_real         = EXCLUDED.is_real,
            ack             = EXCLUDED.ack,
            roi_pixels      = EXCLUDED.roi_pixels,
            footprint       = EXCLUDED.footprint,
            clip_file_id    = EXCLUDED.clip_file_id,
            poster_file_id  = EXCLUDED.poster_file_id,
            frames_manifest = EXCLUDED.frames_manifest,
            meta            = EXCLUDED.meta;
    """)
    with session_scope() as s:
        s.execute(q, payload)

def update_incident(incident_id: str, updates: Dict[str, Any]) -> bool:
    if DRY_RUN:
        _spool("incidents_update", {"incident_id": incident_id, **updates})
        return True

    sets = []
    params: Dict[str, Any] = {"incident_id": incident_id}

    def add(name, val, expr=None, cast=None):
        if val is None and name not in (
            "ended_at","duration_sec","frame_end",
            "clip_file_id","poster_file_id","severity","is_real","ack"
        ):
            return
        params[name] = val
        if expr:
            sets.append(expr)
        else:
            if cast:
                sets.append(f"{name}=CAST(:{name} AS {cast})")
            else:
                sets.append(f"{name}=:{name}")

    add("mission_id", updates.get("mission_id"))
    add("device_id", updates.get("device_id"))
    add("anomaly", updates.get("anomaly"))
    add("started_at", updates.get("started_at"), cast="timestamptz")
    add("ended_at", updates.get("ended_at"), cast="timestamptz")
    add("duration_sec", updates.get("duration_sec"))
    add("frame_start", updates.get("frame_start"))
    add("frame_end", updates.get("frame_end"))
    add("severity", updates.get("severity"))
    add("is_real", updates.get("is_real"))
    add("ack", updates.get("ack"))  # ✅ NEW
    # geo/json
    if "roi_pixels" in updates:
        params["roi_pixels"] = _ensure_json_text(updates["roi_pixels"])
        sets.append("roi_pixels=CAST(:roi_pixels AS jsonb)")
    if "footprint" in updates:
        fp = updates["footprint"]
        params["footprint"] = (None if not fp else fp)
        sets.append(
            "footprint = CASE "
            "WHEN NULLIF(CAST(:footprint AS text), '') IS NULL THEN NULL::geometry "
            "ELSE ST_GeomFromText(CAST(:footprint AS text), 4326) END"
        )
    add("clip_file_id", updates.get("clip_file_id"))
    add("poster_file_id", updates.get("poster_file_id"))
    if "frames_manifest" in updates:
        params["frames_manifest"] = _ensure_json_text(updates["frames_manifest"])
        sets.append("frames_manifest=CAST(:frames_manifest AS jsonb)")
    if "meta" in updates:
        params["meta"] = _ensure_json_text(updates["meta"])
        sets.append("meta=CAST(:meta AS jsonb)")

    if not sets:
        return True

    q = text(f"""
        UPDATE incidents
        SET {', '.join(sets)}
        WHERE incident_id=:incident_id
        RETURNING incident_id;
    """)
    with session_scope() as s:
        row = s.execute(q, params).first()
        return bool(row)

def list_incidents(device_id: Optional[str], mission_id: Optional[int],
                   anomaly: Optional[int],
                   time_from: Optional[str], time_to: Optional[str],
                   limit: int) -> List[Dict[str, Any]]:
    if DRY_RUN:
        return []
    filters, params = [], {"limit": limit}
    if device_id:
        filters.append("i.device_id=:device_id"); params["device_id"]=device_id
    if mission_id:
        filters.append("i.mission_id=:mission_id"); params["mission_id"]=mission_id
    if anomaly:
        filters.append("i.anomaly=:anomaly"); params["anomaly"]=anomaly
    if time_from:
        filters.append("i.started_at>=CAST(:time_from AS timestamptz)"); params["time_from"]=time_from
    if time_to:
        filters.append("i.started_at<CAST(:time_to AS timestamptz)"); params["time_to"]=time_to
    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    q = text(f"""
        SELECT i.incident_id, i.device_id, i.mission_id, i.anomaly,
               i.started_at, i.ended_at, i.duration_sec,
               i.severity, i.is_real, i.ack,
               i.clip_file_id, i.poster_file_id
        FROM incidents i
        {where}
        ORDER BY i.started_at DESC
        LIMIT :limit;
    """)
    with session_scope() as s:
        rows = s.execute(q, params).mappings().all()
        return [dict(r) for r in rows]
