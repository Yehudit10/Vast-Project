from fastapi import APIRouter, Depends
from app.auth import require_token
from app.tables.files.router import router as files_router

api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])
api.include_router(files_router)  

