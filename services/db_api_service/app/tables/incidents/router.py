from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Query,Body

from .schema import (
    IncidentCreate, IncidentUpsert, IncidentUpdate, IncidentRow,
    FrameCreate, FramesBulk, FrameRow
)
from . import repo

router = APIRouter(prefix="/incidents", tags=["incidents"])

# ---- Incidents ----

@router.post("", status_code=201)
def create_incident(payload: IncidentCreate):
    repo.create_incident(payload.model_dump())
    return {"status": "ok"}


@router.put("", status_code=200)
def upsert_incident(payload: IncidentUpsert):
    repo.upsert_incident(payload.model_dump())
    return {"status": "ok"}


# @router.patch("/{incident_id}")
# def update_incident(incident_id: str, payload: IncidentUpdate):
#     ok = repo.update_incident(incident_id, payload.model_dump(exclude_unset=True))
#     if not ok:
#         raise HTTPException(status_code=404, detail="not found")
#     return {"status": "ok"}


@router.patch("")
def patch_row(body: Dict[str, Any] = Body(...)):
    """
    Generic PATCH endpoint for incidents.
    Accepts JSON like:
    {
      "keys": {"incident_id": "..."},
      "data": {"ended_at": "...", "duration_sec": 176, "severity": 3}
    }
    """
    keys = body.get("keys") or {}
    data = body.get("data") or {}

    if not isinstance(keys, dict) or not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="'keys' and 'data' must be objects")

    incident_id = keys.get("incident_id")
    if not incident_id:
        raise HTTPException(status_code=400, detail="Missing 'incident_id' in keys")

    try:
        ok = repo.update_incident(incident_id, data)
        if not ok:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"status": "ok"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{incident_id}", response_model=Optional[IncidentRow])
def get_incident(incident_id: str):
    row = repo.get_incident(incident_id)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row


@router.get("", response_model=list[IncidentRow])
def list_incidents(
    device_id: Optional[str] = None,
    mission_id: Optional[int] = None,
    anomaly: Optional[int] = None,
    time_from: Optional[str] = Query(None, description="ISO8601"),
    time_to: Optional[str] = Query(None, description="ISO8601"),
    limit: int = Query(50, ge=1, le=500),
):
    return repo.list_incidents(device_id, mission_id, anomaly, time_from, time_to, limit)


@router.delete("/{incident_id}")
def delete_incident(incident_id: str):
    ok = repo.delete_incident(incident_id)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "deleted"}

# ---- Frames ----

@router.post("/{incident_id}/frames", status_code=201)
def add_frame(incident_id: str, payload: FrameCreate):
    # repo.insert_frame(incident_id, payload.model_dump())
    return {"status": "ok"}


@router.post("/{incident_id}/frames:bulk", status_code=201)
def add_frames_bulk(incident_id: str, payload: FramesBulk):
    repo.bulk_insert_frames(incident_id, [f.model_dump() for f in payload.frames])
    return {"status": "ok"}


@router.get("/{incident_id}/frames", response_model=list[FrameRow])
def list_frames(
    incident_id: str,
    start_idx: Optional[int] = None,
    end_idx: Optional[int] = None,
    time_from: Optional[str] = Query(None, description="ISO8601"),
    time_to: Optional[str] = Query(None, description="ISO8601"),
    limit: int = Query(1000, ge=1, le=10000),
):
    return repo.list_frames(incident_id, start_idx, end_idx, time_from, time_to, limit)


@router.delete("/{incident_id}/frames")
def delete_frames(incident_id: str, start_idx: Optional[int] = None, end_idx: Optional[int] = None):
    n = repo.delete_frames(incident_id, start_idx, end_idx)
    return {"deleted": n}
