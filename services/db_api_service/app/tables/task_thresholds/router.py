from typing import List, Optional
from fastapi import APIRouter, HTTPException, Body, Query
from . import repo

router = APIRouter(prefix="/task_thresholds", tags=["task_thresholds"])

@router.post("", status_code=201)
def upsert_threshold(
    task: str,
    label: Optional[str] = "",
    threshold: float = Body(..., embed=True),
    updated_by: Optional[str] = Body(None, embed=True),
):
    try:
        repo.upsert_one(task, label or "", threshold, updated_by)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/batch", status_code=201)
def upsert_thresholds_batch(items: List[dict] = Body(...)):
    """
    items: [{"task":"ripeness","label":"","threshold":0.8,"updated_by":"gui"}, ...]
    """
    try:
        return repo.upsert_batch(items)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
