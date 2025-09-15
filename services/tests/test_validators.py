from services.rover_ingest.schema import ImageMeta
from services.rover_ingest.validators import validate_semantics

# Monkey-patch: avoid real MinIO in unit tests
import services.rover_ingest.storage_minio as storage_minio
storage_minio.object_exists = lambda key: True

def test_validate_semantics_ok():
    meta = ImageMeta.parse_obj({
        "schema_ver": 1,
        "device_id": "r1",
        "image_id": "img-2",
        "captured_at": "2025-01-01T10:00:00Z",
        "gps": {"lat": 31.0, "lon": 35.0},
        "heading_deg": 10.0,
        "s3_key": "rover-images/r1/2025/01/01/img-2.jpg",
        "meta_src": "manifest"
    })
    validate_semantics(meta)
