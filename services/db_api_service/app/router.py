# app/router.py
from fastapi import APIRouter, Depends
from app.auth import require_auth
from app.tables.files.router import router as files_router
from app.tables.generic.router import build_generic_router

def build_router(contract_store) -> APIRouter:
    api = APIRouter(
        prefix="/api",
        tags=["api"],
        dependencies=[Depends(require_auth)],
    )

    api.include_router(files_router)

    # הראוטר הגנרי – מקבל את ה-contract_store
    api.include_router(build_generic_router(contract_store))

    return api
