from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from . import schemas, repo

router = APIRouter(prefix="/ripeness_weekly_rollups_ts", tags=["ripeness_weekly_rollups_ts"])

@router.get("", response_model=List[schemas.RipenessWeeklyRollupRead])
def list_rollups(
    from_ts: Optional[str] = Query(None, description="Filter from timestamp (ISO8601)"),
    to_ts: Optional[str] = Query(None, description="Filter to timestamp (ISO8601)"),
):
    try:
        rows = repo.list_rollups(from_ts=from_ts, to_ts=to_ts)
        return rows
    except Exception as e:
        print(f"[ERROR][router] list_rollups failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/{id}", response_model=schemas.RipenessWeeklyRollupRead)
def get_rollup(id: int):
    row = repo.get_rollup(id)
    if not row:
        raise HTTPException(status_code=404, detail="Rollup not found")
    return row

