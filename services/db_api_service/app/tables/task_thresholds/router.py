from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from .schemas import TaskThresholdCreate, TaskThresholdUpdate
from . import repo

router = APIRouter(prefix="/task_thresholds", tags=["task_thresholds"])

@router.post("", status_code=201)
def create_or_upsert_threshold(payload: TaskThresholdCreate):
    repo.upsert_threshold(payload.model_dump())
    return {"status": "ok"}

@router.post("/batch", status_code=201)
def bulk_upsert_thresholds(payload: List[TaskThresholdCreate]):
    if not payload:
        return {"affected_rows": 0}
    count = repo.upsert_batch([p.model_dump() for p in payload])
    return {"affected_rows": count}

@router.put("/{mission_id}/{task}/{label}")
def update_threshold(mission_id: str, task: str, label: str, payload: TaskThresholdUpdate):
    ok = repo.update_threshold(mission_id, task, label, payload.model_dump(exclude_unset=True))
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "ok"}

@router.get("/{mission_id}/{task}/{label}")
def get_threshold(mission_id: str, task: str, label: str):
    row = repo.get_threshold(mission_id, task, label)
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    return row

@router.get("")
def list_thresholds(
    mission_id: Optional[str] = None,
    task: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    return repo.list_thresholds(mission_id, task, limit)

@router.delete("/{mission_id}/{task}/{label}")
def delete_threshold(mission_id: str, task: str, label: str):
    ok = repo.delete_threshold(mission_id, task, label)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"status": "deleted"}
