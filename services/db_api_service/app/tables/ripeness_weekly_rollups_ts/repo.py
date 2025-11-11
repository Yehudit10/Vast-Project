from typing import Optional, Dict, Any, List
from sqlalchemy import text
from app.db import session_scope
from datetime import datetime, timezone

def parse_ts(s: str) -> datetime:
    # תומך ב-"Z" (UTC) וב־offsets. אם מגיעה מחרוזת בלי טיים-זון – נכפה UTC.
    if s.endswith("Z"):
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def list_rollups(from_ts: str | None = None, to_ts: str | None = None) -> List[Dict[str, Any]]:
    q = """
        SELECT *
        FROM ripeness_weekly_rollups_ts
        WHERE 1=1
    """
    params: Dict[str, Any] = {}

    if from_ts:
        q += " AND ts >= :from_ts"
        params["from_ts"] = parse_ts(from_ts)
    if to_ts:
        q += " AND ts <= :to_ts"
        params["to_ts"] = parse_ts(to_ts)

    q += " ORDER BY ts DESC"

    with session_scope() as s:
        rows = s.execute(text(q), params).mappings().all()
        return [dict(r) for r in rows]

def get_rollup(id: int) -> Optional[Dict[str, Any]]:
    sql = text("""
        SELECT id, ts, window_start, window_end, fruit_type, device_id,
               run_id, cnt_total, cnt_ripe, cnt_unripe, cnt_overripe, pct_ripe
        FROM public.ripeness_weekly_rollups_ts
        WHERE id = :id
    """)
    with session_scope() as s:
        row = s.execute(sql, {"id": id}).mappings().first()
    return dict(row) if row else None
