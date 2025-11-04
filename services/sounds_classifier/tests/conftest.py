import sys
import pathlib
import os
import pytest

# 1) Ensure "src" is on sys.path so `import classification...` works
#    This walks up from tests/ to repo root and prepends <root>/src
HERE = pathlib.Path(__file__).resolve()
ROOT = HERE
for _ in range(6):  # walk up a few levels just in case
    if (ROOT / "src").exists():
        sys.path.insert(0, str(ROOT / "src"))
        break
    ROOT = ROOT.parent

# 2) Provide minimal, isolated env defaults for tests
@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    # Core runtime defaults
    monkeypatch.setenv("DEVICE", "cpu")
    monkeypatch.setenv("BACKBONE", "cnn14")

    # Windowing / aggregation
    monkeypatch.setenv("WINDOW_SEC", "2.0")
    monkeypatch.setenv("HOP_SEC", "0.5")
    monkeypatch.setenv("PAD_LAST", "true")
    monkeypatch.setenv("AGG", "mean")
    monkeypatch.setenv("UNKNOWN_THRESHOLD", "0.55")

    # Disable optional integrations by default
    monkeypatch.setenv("KAFKA_BROKERS", "")
    monkeypatch.delenv("WRITE_DB", raising=False)
    monkeypatch.delenv("DB_URL", raising=False)

    # HEAD path (tests can override with real/mocked head if needed)
    head_dir = tmp_path / "head"
    head_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HEAD", str(head_dir / "dummy.joblib"))
    # Let tests decide labels source; default to none
    monkeypatch.setenv("LABELS_CSV", "")
    monkeypatch.delenv("HEAD_META", raising=False)

    # MinIO defaults (won't be used unless explicitly mocked)
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "minio")
    monkeypatch.setenv("MINIO_SECRET_KEY", "minio123")
    monkeypatch.setenv("MINIO_SECURE", "false")

    # Kafka alerts defaults
    monkeypatch.setenv("ALERTS_TOPIC", "dev-robot-alerts")

    # Checkpoint defaults (tests typically mock loading; real file not needed)
    monkeypatch.setenv("CHECKPOINT", str(tmp_path / "models" / "panns_data" / "Cnn14_mAP=0.431.pth"))
    monkeypatch.delenv("CHECKPOINT_URL", raising=False)

    yield
