from __future__ import annotations
from typing import Any, Dict, List, Optional
from datetime import datetime
from sqlalchemy import text
from app.db import session_scope


def list_alerts(
    limit: int = 100,
    offset: int = 0,
    device_id: Optional[str] = None,
    alert_type: Optional[str] = None,
    ts_from: Optional[datetime] = None,
    ts_to: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """
    Returns alerts with basic optional filters and pagination.
    """
    q = """
        SELECT
            alert_id, alert_type, device_id, started_at, ended_at, confidence, area,
            lat, lon, severity, image_url, vod, hls, ack, meta, created_at, updated_at
        FROM alerts
        WHERE (:device_id::text IS NULL OR device_id = :device_id)
          AND (:alert_type::text IS NULL OR alert_type = :alert_type)
          AND (:ts_from::timestamptz IS NULL OR started_at >= :ts_from)
          AND (:ts_to::timestamptz IS NULL OR started_at <= :ts_to)
        ORDER BY started_at DESC
        LIMIT :limit OFFSET :offset
    """
    with session_scope() as s:
        res = s.execute(
            text(q),
            {
                "device_id": device_id,
                "alert_type": alert_type,
                "ts_from": ts_from,
                "ts_to": ts_to,
                "limit": int(limit),
                "offset": int(offset),
            },
        )
        return [dict(row._mapping) for row in res.fetchall()]


def _get_alert_min(alert_id: int) -> Optional[Dict[str, Any]]:
    """
    Returns minimal alert fields required for fallback joins.
    """
    q = """
        SELECT alert_id, device_id, started_at, ended_at, meta
        FROM alerts
        WHERE alert_id = :alert_id
    """
    with session_scope() as s:
        row = s.execute(text(q), {"alert_id": int(alert_id)}).mappings().first()
        return dict(row) if row else None


def _images_by_rp_alert_id(alert_id: int) -> List[Dict[str, Any]]:
    """
    Preferred join: ripeness_predictions.alert_id → alerts.alert_id
    """
    q = """
        SELECT il.inference_log_id, il.image_url, il.created_at
        FROM ripeness_predictions rp
        JOIN inference_logs il
          ON il.inference_log_id = rp.inference_log_id
        WHERE rp.alert_id = :alert_id
        ORDER BY il.created_at ASC NULLS LAST, il.inference_log_id ASC
    """
    with session_scope() as s:
        res = s.execute(text(q), {"alert_id": int(alert_id)})
        return [dict(r._mapping) for r in res.fetchall()]


def _images_by_device_and_run(alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fallback 1: join by device_id + run_id where run_id is taken from alerts.meta->>'run_id'.
    """
    q = """
        SELECT il.inference_log_id, il.image_url, il.created_at
        FROM alerts a
        JOIN ripeness_predictions rp
          ON rp.device_id = a.device_id
         AND rp.run_id = (a.meta->>'run_id')
        JOIN inference_logs il
          ON il.inference_log_id = rp.inference_log_id
        WHERE a.alert_id = :alert_id
        ORDER BY il.created_at ASC NULLS LAST, il.inference_log_id ASC
    """
    with session_scope() as s:
        res = s.execute(text(q), {"alert_id": int(alert["alert_id"])})
        return [dict(r._mapping) for r in res.fetchall()]


def _images_by_device_and_window(alert: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fallback 2: join by device_id + time window overlap with the alert.
    """
    q = """
        SELECT il.inference_log_id, il.image_url, il.created_at
        FROM ripeness_predictions rp
        JOIN inference_logs il
          ON il.inference_log_id = rp.inference_log_id
        WHERE rp.device_id = :device_id
          AND rp.created_at BETWEEN :started_at AND COALESCE(:ended_at, NOW())
        ORDER BY il.created_at ASC NULLS LAST, il.inference_log_id ASC
    """
    with session_scope() as s:
        res = s.execute(
            text(q),
            {
                "device_id": alert["device_id"],
                "started_at": alert["started_at"],
                "ended_at": alert["ended_at"],
            },
        )
        return [dict(r._mapping) for r in res.fetchall()]


def list_alert_images(alert_id: int) -> List[Dict[str, Any]]:
    """
    Returns images for a specific alert with progressive fallback:
    1) By ripeness_predictions.alert_id
    2) By device_id + run_id (meta->>'run_id')
    3) By device_id + time window
    """
    # Try the preferred direct linkage
    try:
        imgs = _images_by_rp_alert_id(alert_id)
        if imgs:
            return imgs
    except Exception:
        pass  # continue to fallbacks

    alert = _get_alert_min(alert_id)
    if not alert:
        return []

    # Fallback 1: device + run_id
    try:
        imgs = _images_by_device_and_run(alert)
        if imgs:
            return imgs
    except Exception:
        pass

    # Fallback 2: device + time window
    try:
        imgs = _images_by_device_and_window(alert)
        if imgs:
            return imgs
    except Exception:
        pass

    return []
