# services/mqtt_gateway/tests/test_mapper.py
# Purpose: Unit tests for pure mapping logic (no MinIO/Kafka).
# Run: pytest -q

from services.mqtt_gateway.models import ImageInfo
from services.mqtt_gateway.mapper import build_minio_key, map_to_objects


def test_build_minio_key_happy():
    key = build_minio_key("camera-01", 1761548130123, "foo.jpg")
    assert key.startswith("images/camera-01/2025/10/27/")
    assert key.endswith("camera-01_1761548130123.jpg")


def test_build_minio_key_ext_fallback():
    key = build_minio_key("s1", 1000, "noext")
    assert key.endswith("s1_1000.jpg")


def test_map_to_objects_event_and_key():
    info = ImageInfo(
        sensor_id="camera-01",
        captured_ts=1761548130123,
        filename="garage_cam_01_20251027_121530.jpg",
        content_type="image/jpeg",
    )
    mobj, kev = map_to_objects("rover-images", info, sha256="abc", size_bytes=123)
    assert mobj.bucket == "rover-images"
    assert mobj.key.endswith("camera-01_1761548130123.jpg")
    assert mobj.sha256 == "abc"
    assert kev.image.key == mobj.key
    assert kev.key == "camera-01:1761548130123"
    assert kev.version == 1
