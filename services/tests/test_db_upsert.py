# services/rover_ingest/tests/test_db_upsert.py
import os
import pytest
from services.rover_ingest.db import upsert
from services.rover_ingest.schema import ImageMeta
from services.rover_ingest import storage_minio

requires_db = pytest.mark.skipif(
    not os.getenv("PG_DSN"), reason="PG_DSN not set"
)

@requires_db
def test_upsert_idempotent(monkeypatch):
    monkeypatch.setattr(storage_minio, "object_exists", lambda key: True)
    meta = ImageMeta.model_validate({
        "schema_ver": 1,
        "device_id": "rover-07",
        "image_id": "20250910T101500Z-abc123",
        "captured_at": "2025-09-10T10:15:00Z",
        "gps": {"lat": 31.7, "lon": 35.2},
        "s3_key": "rover-07/2025/09/10/20250910T101500Z-abc123.jpg",
        "meta_src": "manifest",
    })
    upsert(meta)
    upsert(meta) 