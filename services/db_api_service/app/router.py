from fastapi import APIRouter, Depends
from app.auth import require_auth
from app.tables.files.router import router as files_router

api = APIRouter(prefix="/api", tags=["api"], dependencies=[Depends(require_auth)])

api.include_router(files_router)

@api.get("/me")
def me(principal = Depends(require_auth)):
    kind, obj = principal
    if kind == "user":
        return {"type": "user", "id": obj.id, "username": obj.username}
    else:
        return {"type": "service", "name": obj.name}
