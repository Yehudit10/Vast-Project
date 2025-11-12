from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from . import repo

router = APIRouter(prefix="/tables/alerts", tags=["alerts"])


@router.get("")
def get_alerts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    device_id: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    ts_from: Optional[datetime] = Query(None, description="ISO timestamp"),
    ts_to: Optional[datetime] = Query(None, description="ISO timestamp"),
) -> Dict[str, Any]:
    """
    Returns alerts (paginated). Filters are optional.
    """
    try:
        items = repo.list_alerts(
            limit=limit,
            offset=offset,
            device_id=device_id,
            alert_type=alert_type,
            ts_from=ts_from,
            ts_to=ts_to,
        )
        return {"items": items, "limit": limit, "offset": offset, "count": len(items)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{alert_id}/images")
def get_alert_images(alert_id: int) -> Dict[str, Any]:
    """
    Returns images for a single alert using joins:
    ripeness_predictions → inference_logs(image_url),
    with fallbacks (device+run_id, device+time window).
    """
    try:
        images = repo.list_alert_images(alert_id)
        if images is None:
            images = []
        return {"alert_id": alert_id, "images": images, "count": len(images)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
