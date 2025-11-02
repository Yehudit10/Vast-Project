
# api = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(require_auth)])

# api.include_router(files_router)

# @api.get("/me")
# def me(principal = Depends(require_auth)):
#     kind, obj = principal
#     if kind == "user":
#         return {"type": "user", "id": obj.id, "username": obj.username}
#     else:
#         return {"type": "service", "name": obj.name}

# app/router.py

from fastapi import APIRouter, Depends
from app.auth import require_auth
from app.tables.files.router import router as files_router
from app.tables.generic.router import build_generic_router
from app.tables.task_thresholds.router import router as task_thresholds_router


def build_router(contract_store) -> APIRouter:
    api = APIRouter(
        prefix="/api",
        tags=["api"],
        dependencies=[Depends(require_auth)],
    )

    api.include_router(files_router)
    api.include_router(task_thresholds_router)
    api.include_router(build_generic_router(contract_store))

    return api
ם