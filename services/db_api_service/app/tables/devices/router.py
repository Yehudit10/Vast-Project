from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from .schemas import DeviceOut, DeviceList
from . import repo

# Create API router for devices
router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=DeviceList)
def list_devices(
    limit: int = Query(50, ge=1, le=500, description="Maximum number of devices to return"),
    offset: int = Query(0, ge=0, description="Number of devices to skip for pagination"),
    q: Optional[str] = Query(None, description="Free text search in device_id, model, or owner"),
    active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """
    API endpoint to retrieve a list of devices with optional filters.
    
    Query Parameters:
        - limit: Maximum number of records (default: 50, max: 500).
        - offset: Records to skip for pagination (default: 0).
        - q: Free-text search across device_id, model, and owner.
        - active: Filter devices by active status.

    Returns:
        DeviceList: Paginated list of devices with total count.
    """
    return repo.list_devices(limit=limit, offset=offset, q=q, active=active)


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: str):
    """
    API endpoint to retrieve a single device by its ID.

    Args:
        device_id (str): Unique identifier of the device.

    Raises:
        HTTPException: 404 if the device is not found.

    Returns:
        DeviceOut: Device details if found.
    """
    row = repo.get_device(device_id)
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return row