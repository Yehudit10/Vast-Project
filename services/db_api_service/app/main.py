from fastapi import FastAPI
from app.router import api
from app.auth import router as auth_router
from app.db import engine
from app.models import Base

app = FastAPI(title="Storage DB API", version="1.1.0")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    Base.metadata.create_all(bind=engine)
    return {"ready": True}

app.include_router(auth_router)
app.include_router(api)

