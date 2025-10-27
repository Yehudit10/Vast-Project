import os
import shutil
import tempfile
import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("ENV", "dev")
os.environ.setdefault("DB_DRY_RUN", "1")
os.environ.setdefault("DB_DSN", "sqlite+pysqlite:///:memory:")

SPOOL_BASE = tempfile.mkdtemp(prefix="api_spool_combined_")
os.environ["DRY_RUN_SPOOL"] = SPOOL_BASE

from app.main import app
import app.auth as auth_mod


@pytest.fixture(scope="session")
def client_raw():
    with TestClient(app) as c:
        r0 = c.get("/ready")
        assert r0.status_code == 200 and r0.json().get("ready") is True
        yield c


@pytest.fixture()
def client_overridden_auth():
   
    from types import SimpleNamespace
    app.dependency_overrides[auth_mod.require_auth] = lambda: ("service", SimpleNamespace(name="tests"))
    try:
        with TestClient(app) as c:
            # גם כאן נוודא מוכנות (ליתר בטחון)
            r0 = c.get("/ready")
            assert r0.status_code == 200 and r0.json().get("ready") is True
            yield c
    finally:
        app.dependency_overrides.pop(auth_mod.require_auth, None)


@pytest.fixture(scope="session")
def bootstrap_tokens(client_raw):
    
    r0 = client_raw.get("/ready")
    assert r0.status_code == 200 and r0.json().get("ready") is True

    body = {"service_name": "svc-tests-unified", "rotate_if_exists": True}
    r = client_raw.post("/auth/_dev_bootstrap", json=body)
    assert r.status_code == 201, f"bootstrap failed: {r.status_code} {r.text}"
    data = r.json()
    return {
        "access_token": data["tokens"]["access_token"],
        "refresh_token": data["tokens"]["refresh_token"],
        "service_raw": data["service_account"]["raw_token"] or data["service_account"]["token"],
        "service_name": data["service_account"]["name"],
    }


def teardown_module(module=None):
    try:
        shutil.rmtree(SPOOL_BASE, ignore_errors=True)
    except Exception:
        pass
