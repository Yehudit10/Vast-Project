# from app.router import api

# app.include_router(api)

from fastapi import FastAPI
from app.auth import router as auth_router
from app.db import engine
from app.models import Base
from app.contracts.loader import ContractStore
from app.router import build_router
from app.tables.generic import repo
from .config import settings

contract_store = ContractStore(settings.CONTRACTS_DIR)
repo.set_contract_store(contract_store)

app = FastAPI(title="Storage DB API", version="1.1.0")

@app.on_event("startup")
def load_contracts_on_startup():
    contract_store.load_all()

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/ready")
def ready():
    Base.metadata.create_all(bind=engine)
    return {"ready": True}

app.include_router(auth_router)

app.include_router(build_router(contract_store))


