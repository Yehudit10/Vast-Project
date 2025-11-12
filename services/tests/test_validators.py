# from services.rover_ingest.schema import ImageMeta
# from services.rover_ingest.validators import validate_semantics

# # Monkey-patch: avoid real MinIO in unit tests
# import services.rover_ingest.storage_minio as storage_minio
# storage_minio.object_exists = lambda key: True

# def test_validate_semantics_ok():
#     meta = ImageMeta.parse_obj({
#         "schema_ver": 1,
#         "device_id": "r1",
#         "image_id": "img-2",
#         "captured_at": "2025-01-01T10:00:00Z",
#         "gps": {"lat": 31.0, "lon": 35.0},
#         "heading_deg": 10.0,
#         "s3_key": "rover-images/r1/2025/01/01/img-2.jpg",
#         "meta_src": "manifest"
#     })
#     validate_semantics(meta)

# services/rover_ingest/tests/test_validators.py
import pytest
from types import SimpleNamespace
from services.rover_ingest.validators import validate_semantics

def test_validate_semantics_passes_when_object_exists(monkeypatch):
    meta = SimpleNamespace(
        device_id="rover-07",
        s3_key="rover-07/2025/09/10/20250910T101500Z-abc123.jpg",
        gps=SimpleNamespace(lat=31.7, lon=35.2),
        captured_at=None
    )
    monkeypatch.setenv("MINIO_BUCKET", "rover-images")
    monkeypatch.setenv("MINIO_ENDPOINT", "dummy:9000")

    # מדמים שקובץ קיים
    from services.rover_ingest import storage_minio
    monkeypatch.setattr(storage_minio, "object_exists", lambda key: True)

    validate_semantics(meta)  # לא אמור לזרוק

def test_validate_semantics_raises_when_missing_object(monkeypatch):
    meta = SimpleNamespace(
        device_id="rover-07",
        s3_key="missing.jpg",
        gps=SimpleNamespace(lat=31.7, lon=35.2),
        captured_at=None
    )
    from services.rover_ingest import storage_minio
    monkeypatch.setattr(storage_minio, "object_exists", lambda key: False)

    with pytest.raises(FileNotFoundError):
        validate_semantics(meta)
