# app/router.py
from fastapi import APIRouter, Depends
from app.auth import require_auth
from app.tables.files.router import router as files_router
<<<<<<< HEAD
from app.tables.devices.router import router as device_router
from app.tables.incidents.router import router as incidents_router
=======
from app.tables.generic.router import build_generic_router
from app.tables.task_thresholds.router import router as task_thresholds_router
>>>>>>> c2d14fa33488ec8d7ead3ec98c4d532094712632


<<<<<<< HEAD
api.include_router(files_router)
api.include_router(device_router)
api.include_router(incidents_router)
=======
def build_router(contract_store) -> APIRouter:
    api = APIRouter(
        prefix="/api",
        tags=["api"],
        dependencies=[Depends(require_auth)],
    )
>>>>>>> c2d14fa33488ec8d7ead3ec98c4d532094712632

    api.include_router(files_router)
    api.include_router(task_thresholds_router)
    api.include_router(build_generic_router(contract_store))

    return api
