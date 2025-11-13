# tests/conftest.py
import os
import pytest
from sqlalchemy import text
from agri_baseline.src.pipeline.db import get_engine

@pytest.fixture(autouse=True, scope="function")
def _ensure_local_db_url(monkeypatch):
    """
    Guarantee DATABASE_URL exists for tests.
    """
    monkeypatch.setenv(
        "DATABASE_URL",
        os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg2://missions_user:pg123@localhost:5432/missions_db",
        ),
    )

@pytest.fixture(autouse=True)
def _clean_tables_before_test():
    """
    Clean key tables before each test so counts can increase deterministically.
    Adjust the list to your schema.
    """
    tables = ["anomalies", "tile_stats", "event_logs"]
    with get_engine().begin() as conn:
        for t in tables:
            conn.execute(text(f"DELETE FROM {t}"))
