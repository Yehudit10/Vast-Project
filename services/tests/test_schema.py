# from services.rover_ingest.schema import ImageMeta

# def test_parse_valid_minimal():
#     payload = {
#         "schema_ver": 1,
#         "device_id": "r1",
#         "image_id": "img-1",
#         "captured_at": "2025-01-01T10:00:00Z",
#         "gps": {"lat": 31.0, "lon": 35.0},
#         "heading_deg": 370.0,
#         "alt_m": 1.2,
#         "s3_key": "rover-images/r1/2025/01/01/img-1.jpg",
#         "meta_src": "manifest"
#     }
#     meta = ImageMeta.parse_obj(payload)
#     assert 0.0 <= meta.heading_deg < 360.0

# def test_missing_required_raises():
#     bad = {"device_id": "r1"}
#     try:
#         ImageMeta.parse_obj(bad)
#         assert False, "expected validation error"
#     except Exception:
#         assert True

# services/rover_ingest/tests/test_schema.py
import datetime as dt
import pytest
from pydantic import BaseModel, field_validator
from services.rover_ingest.schema import ImageMeta

def test_valid_payload_parses():
    payload = {
        "schema_ver": 1,
        "device_id": "rover-07",
        "image_id": "20250910T101500Z-abc123",
        "captured_at": "2025-09-10T10:15:00Z",
        "gps": {"lat": 31.7767, "lon": 35.2345},
        "s3_key": "rover-07/2025/09/10/20250910T101500Z-abc123.jpg",
        "meta_src": "manifest",
    }
    m = ImageMeta.model_validate(payload)
    assert m.device_id == "rover-07"
    assert m.captured_at.tzinfo is not None

def test_missing_required_field_fails():
    with pytest.raises(Exception):
        ImageMeta.model_validate({"schema_ver": 1})
