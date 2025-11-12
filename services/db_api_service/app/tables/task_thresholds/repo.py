from __future__ import annotations
from typing import Any, Dict, List, Tuple,Optional
from sqlalchemy import text
from app.db import session_scope

def list_all() -> list[dict]:
    q = text("""
        SELECT
            task::text   AS task,
            label,
            threshold,
            updated_by,
            updated_at
        FROM task_thresholds
        ORDER BY task, label;
    """)
    with session_scope() as s:
        rows = s.execute(q).mappings().all()
        return [dict(r) for r in rows]

def get_one(task: str, label: Optional[str] = "") -> Optional[dict]:
    # If you maintain a unique (task, label) pair – keep label; otherwise label can be ignored
    q = text("""
        SELECT
            task::text   AS task,
            label,
            threshold,
            updated_by,
            updated_at
        FROM task_thresholds
        WHERE task = CAST(:task AS task_type_enum)
          AND label = :label
        LIMIT 1;
    """)
    with session_scope() as s:
        row = s.execute(q, {"task": task, "label": label or ""}).mappings().first()
        return dict(row) if row else None


def upsert_one(task: str, label: str, threshold: float, updated_by: str | None) -> None:
    q = text("""
        INSERT INTO task_thresholds (task, label, threshold, updated_by)
        VALUES (CAST(:task AS task_type_enum), :label, :threshold, :updated_by)
        ON CONFLICT (task, label)
        DO UPDATE SET
            threshold  = EXCLUDED.threshold,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW();
    """)
    with session_scope() as s:
        s.execute(q, {
            "task": task, "label": label or "", "threshold": float(threshold),
            "updated_by": updated_by,
        })

def upsert_batch(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    items: [{"task": "...", "label": "", "threshold": 0.8, "updated_by": "gui"}, ...]
    מחזיר {"ok": [[task,label], ...], "fail": [[[task,label], "reason"], ...]}
    """
    ok: List[List[str]] = []
    fail: List[List[Any]] = []
    if not items:
        return {"ok": ok, "fail": fail}

    q = text("""
        INSERT INTO task_thresholds (task, label, threshold, updated_by)
        VALUES (CAST(:task AS task_type_enum), :label, :threshold, :updated_by)
        ON CONFLICT (task, label)
        DO UPDATE SET
            threshold  = EXCLUDED.threshold,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW();
    """)

    with session_scope() as s:
        for it in items:
            task = str(it.get("task", ""))
            label = str(it.get("label") or "")
            try:
                s.execute(q, {
                    "task": task,
                    "label": label,
                    "threshold": float(it["threshold"]),
                    "updated_by": it.get("updated_by"),
                })
                ok.append([task, label])
            except Exception as e:
                fail.append([[task, label], str(e)])
    return {"ok": ok, "fail": fail}
