from typing import Any, Dict, List, Optional
from sqlalchemy import text
from app.db import session_scope
import os, json, time, pathlib

DRY_RUN = os.getenv("DB_DRY_RUN", "0") == "1"
SPOOL_DIR = os.getenv("DRY_RUN_SPOOL", "/tmp/api_spool")


def _spool(name: str, payload: Dict[str, Any]):
    p = pathlib.Path(SPOOL_DIR)
    p.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    (p / f"{ts}-{name}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def upsert_threshold(payload: Dict[str, Any]) -> None:
    """
    Insert or update threshold row by (task, label).
    Automatically updates timestamp and updated_by.
    """
    q = text("""
        INSERT INTO task_thresholds (task, label, threshold, updated_by)
        VALUES (CAST(:task AS task_type_enum), COALESCE(:label, ''), :threshold, :updated_by)
        ON CONFLICT (task, label)
        DO UPDATE SET
            threshold  = EXCLUDED.threshold,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW();
    """)
    with session_scope() as s:
        s.execute(q, payload)




from typing import Any, Dict, List
from sqlalchemy import text
from app.db import session_scope

def upsert_batch(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Bulk UPSERT by (task, label) with ENUM cast.
    Input item keys: task, label (optional -> ''), threshold, updated_by (optional).
    Returns: {"ok": [(task,label), ...], "fail": [((task,label), reason), ...]}
    """
    report = {"ok": [], "fail": []}
    if not items:
        return report

    # normalize & validate locally (fast fail)
    norm: List[Dict[str, Any]] = []
    seen_keys = set()
    for it in items:
        task = (it.get("task") or "").strip()
        label = (it.get("label") or "").strip()
        updated_by = (it.get("updated_by") or None)
        thr = it.get("threshold")

        if not task:
            report["fail"].append(((task, label), "task-empty"))
            continue
        try:
            thr_f = float(thr)
        except Exception:
            report["fail"].append(((task, label), "threshold-not-float"))
            continue
        if not (0.0 <= thr_f <= 1.0):
            report["fail"].append(((task, label), "threshold-out-of-range"))
            continue

        key = (task, label)
        if key in seen_keys:
            
            continue
        seen_keys.add(key)

        norm.append({
            "task": task,
            "label": label,
            "threshold": thr_f,
            "updated_by": updated_by,
        })

    if not norm:
        return report

    # single-statement bulk upsert with ENUM cast
    q = text("""
        INSERT INTO task_thresholds (task, label, threshold, updated_by)
        VALUES
        
        (CAST(:task AS task_type_enum), :label, :threshold, :updated_by)
        ON CONFLICT (task, label)
        DO UPDATE SET
            threshold  = EXCLUDED.threshold,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW();
    """)

    try:
        with session_scope() as s:
            s.execute(q, norm)   # execmany
       
        report["ok"] = [(x["task"], x["label"]) for x in norm]
        return report
    except Exception as e:
        # bulk failed (e.g. invalid ENUM value), fallback to per-item upsert
        per_item_q = text("""
            INSERT INTO task_thresholds (task, label, threshold, updated_by)
            VALUES (CAST(:task AS task_type_enum), :label, :threshold, :updated_by)
            ON CONFLICT (task, label)
            DO UPDATE SET
                threshold = EXCLUDED.threshold,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW();
        """)
        for x in norm:
            try:
                with session_scope() as s:
                    s.execute(per_item_q, x)
                report["ok"].append((x["task"], x["label"]))
            except Exception as ie:
                report["fail"].append(((x["task"], x["label"]), str(ie)))
        return report


def update_threshold(mission_id: str, task: str, label: str, updates: Dict[str, Any]) -> bool:
    if DRY_RUN:
        _spool("task_thresholds_update", {
            "mission_id": mission_id, "task": task, "label": label, **updates
        })
        return True

    sets, params = [], {
        "mission_id": mission_id,
        "task_key": task,
        "label_key": label if label is not None else ""
    }

    if "task" in updates and updates["task"]:
        sets.append("task=:task")
        params["task"] = updates["task"]

    if "label" in updates and updates["label"] is not None:
        sets.append("label=:label")
        params["label"] = updates["label"] or ""

    if "threshold" in updates and updates["threshold"] is not None:
        sets.append("threshold=:threshold")
        params["threshold"] = updates["threshold"]

    if "updated_by" in updates and updates["updated_by"] is not None:
        sets.append("updated_by=:updated_by")
        params["updated_by"] = updates["updated_by"]

    if not sets:
        return True

    q = text(f"""
        UPDATE task_thresholds
        SET {', '.join(sets)}, updated_at = now()
        WHERE mission_id=:mission_id AND task=:task_key AND label=:label_key
        RETURNING mission_id;
    """)
    with session_scope() as s:
        row = s.execute(q, params).first()
        return bool(row)


def get_threshold(mission_id: str, task: str, label: str) -> Optional[Dict[str, Any]]:
    if DRY_RUN:
        return None

    q = text("""
        SELECT mission_id, task, label, threshold, updated_at, updated_by
        FROM task_thresholds
        WHERE mission_id=:mission_id AND task=:task AND label=:label
        LIMIT 1;
    """)
    params = {"mission_id": mission_id, "task": task, "label": label or ""}
    with session_scope() as s:
        row = s.execute(q, params).mappings().first()
        return dict(row) if row else None


def list_thresholds(
    mission_id: Optional[str] = None,
    task: Optional[str] = None,
    limit: int = 200
) -> List[Dict[str, Any]]:
    if DRY_RUN:
        return []

    filters, params = [], {"limit": limit}
    if mission_id:
        filters.append("mission_id=:mission_id")
        params["mission_id"] = mission_id
    if task:
        filters.append("task=:task")
        params["task"] = task

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    q = text(f"""
        SELECT mission_id, task, label, threshold, updated_at, updated_by
        FROM task_thresholds
        {where}
        ORDER BY updated_at DESC
        LIMIT :limit;
    """)
    with session_scope() as s:
        rows = s.execute(q, params).mappings().all()
        return [dict(r) for r in rows]


def delete_threshold(mission_id: str, task: str, label: str) -> bool:
    if DRY_RUN:
        _spool("task_thresholds_delete", {
            "mission_id": mission_id, "task": task, "label": label
        })
        return True

    q = text("""
        DELETE FROM task_thresholds
        WHERE mission_id=:mission_id AND task=:task AND label=:label
        RETURNING mission_id;
    """)
    params = {"mission_id": mission_id, "task": task, "label": label or ""}
    with session_scope() as s:
        row = s.execute(q, params).first()
        return bool(row)
