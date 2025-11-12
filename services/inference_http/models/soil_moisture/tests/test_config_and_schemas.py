import os
from app.config import load_zones, Settings
from app.schemas import InferRequest, InferResponse


def test_load_zones_file_exists_and_parses():
    # Use the repo's zones.yaml
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    zones_path = os.path.join(base_dir, "configs", "zones.yaml")
    data = load_zones(zones_path)
    assert isinstance(data, dict)
    assert "zones" in data
    assert isinstance(data["zones"], dict)


def test_settings_defaults_are_present():
    s = Settings()
    # Ensure critical fields exist and are strings/ints
    assert isinstance(s.kafka_brokers, str)
    assert isinstance(s.kafka_topic, str)
    assert isinstance(s.pg_dsn, str)
    assert isinstance(s.decision_window_sec, int)
    assert isinstance(s.patch_size, int)
    assert isinstance(s.patch_stride, int)


def test_schemas_models_construction():
    req = InferRequest(device_id="zone-a", image_b64="abcd==")
    assert req.device_id == "zone-a"
    assert isinstance(req.image_b64, str)

    resp = InferResponse(
        device_id="zone-a",
        dry_ratio=0.5,
        decision="run",
        confidence=0.9,
        patch_count=4,
        ts="2024-01-01T00:00:00Z",
        idempotency_key="zone-a:12345",
    )
    assert resp.decision in {"run", "stop", "noop"}
    assert resp.patch_count == 4

