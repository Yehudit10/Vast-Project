# services/rover_ingest/tests/test_metrics.py
from services.rover_ingest.app import handle_message, INGEST_OK, INGEST_FAIL
from services.rover_ingest import storage_minio
from services.rover_ingest.db import upsert

def test_handle_message_increments_success(monkeypatch):
    payload = {
        "schema_ver": 1,
        "device_id": "rover-07",
        "image_id": "20250910T101500Z-abc123",
        "captured_at": "2025-09-10T10:15:00Z",
        "gps": {"lat": 31.7, "lon": 35.2},
        "s3_key": "rover-07/2025/09/10/20250910T101500Z-abc123.jpg",
        "meta_src": "manifest",
    }
    monkeypatch.setattr(storage_minio, "object_exists", lambda key: True)
    called = {"n": 0}
    monkeypatch.setattr("services.rover_ingest.db.upsert", lambda meta: None)

    before_ok = INGEST_OK._value.get()
    before_fail = INGEST_FAIL._value.get()

    handle_message(payload)

    assert INGEST_OK._value.get() == before_ok + 1
    assert INGEST_FAIL._value.get() == before_fail
