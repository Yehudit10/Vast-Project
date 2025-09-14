from fastapi import FastAPI
from app.router import api

app = FastAPI(title="Storage DB API", version="1.0.0")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    return {"ready": True}

app.include_router(api)
