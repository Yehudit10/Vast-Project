from typing import Optional, Dict, Any
from sqlalchemy import text
from app.db import session_scope


def list_devices(
    limit: int = 50,
    offset: int = 0,
    q: Optional[str] = None,
    active: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Retrieve a paginated list of devices with optional filtering.
    
    Args:
        limit (int): Maximum number of devices to return. Defaults to 50.
        offset (int): Number of records to skip (for pagination). Defaults to 0.
        q (Optional[str]): Search string to filter by device_id, model, or owner.
        active (Optional[bool]): Filter by active status if provided.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - "total": total number of matching devices.
            - "items": list of matching device records as dictionaries.
    """
    filters = []
    params: Dict[str, Any] = {"limit": limit, "offset": offset}

    # Free-text search filter
    if q:
        filters.append(
            "(device_id ILIKE :q OR model ILIKE :q OR owner ILIKE :q)"
        )
        params["q"] = f"%{q}%"

    # Active status filter
    if active is not None:
        filters.append("active = :active")
        params["active"] = active

    # Build WHERE clause dynamically based on filters
    where_sql = f"WHERE {' AND '.join(filters)}" if filters else ""

    # SQL for fetching paginated list
    list_sql = text(f"""
        SELECT device_id, model, owner, active
        FROM public.devices
        {where_sql}
        ORDER BY device_id
        LIMIT :limit OFFSET :offset
    """)

    # SQL for total count
    count_sql = text(f"""
        SELECT COUNT(*)::int AS total
        FROM public.devices
        {where_sql}
    """)

    # Execute both queries within a session scope
    with session_scope() as s:
        total = s.execute(count_sql, params).scalar_one()
        rows = s.execute(list_sql, params).mappings().all()

    return {"total": total, "items": [dict(r) for r in rows]}


def get_device(device_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a single device by its ID.
    
    Args:
        device_id (str): Unique identifier of the device.

    Returns:
        Optional[Dict[str, Any]]: Dictionary containing device details
        if found, otherwise None.
    """
    sql = text("""
        SELECT device_id, model, owner, active
        FROM public.devices
        WHERE device_id = :device_id
    """)
    with session_scope() as s:
        row = s.execute(sql, {"device_id": device_id}).mappings().first()
    return dict(row) if row else None