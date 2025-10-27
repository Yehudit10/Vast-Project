# File: tests/test_app.py
from fastapi.testclient import TestClient
import classification.app as app_mod

# -----------------------------
# Helpers / Fakes
# -----------------------------
class DummyAT:
    """Lightweight fake for AudioTagging to let startup warm-up pass."""
    def __init__(self, *a, **k):
        pass
    def inference(self, x):
        # Return something with "embedding" to match warm-up expectations
        return {"embedding": [0.0, 0.0]}

class DummyConn:
    """Fake psycopg2 connection used by open_db()."""
    def __init__(self):
        self.closed = False
        self._executed = []
    def cursor(self):
        class C:
            def __init__(self, outer):
                self.outer = outer
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
            def execute(self, *a, **k):
                self.outer._executed.append(("EXEC", a, k))
        return C(self)
    def commit(self):
        self._executed.append(("COMMIT", None, None))
    def rollback(self):
        self._executed.append(("ROLLBACK", None, None))
    def close(self):
        self.closed = True

def _patch_startup_and_db(monkeypatch, *, capture):
    """
    Patch all heavy/IO dependencies used by app startup and endpoints.
    'capture' is a dict used to collect calls for assertions.
    """
    # Avoid heavy model loading
    monkeypatch.setattr(app_mod, "AudioTagging", DummyAT, raising=True)
    # Pretend pipeline file does not exist -> skip joblib.load
    monkeypatch.setattr(app_mod.os.path, "exists", lambda p: False, raising=True)

    # open_db returns DummyConn and we keep the instance in capture
    def _open_db():
        conn = DummyConn()
        capture["conn"] = conn
        return conn
    monkeypatch.setattr(app_mod, "open_db", _open_db, raising=True)

    # No-op ensure_run
    monkeypatch.setattr(app_mod, "ensure_run", lambda conn, run_id: None, raising=True)

    # Safe defaults for resolve/upsert; specific tests will override if needed
    monkeypatch.setattr(app_mod, "resolve_file_id", lambda *a, **k: 123, raising=True)

    def _upsert(conn, payload):
        capture.setdefault("upserts", []).append({"conn": conn, "payload": payload})
    monkeypatch.setattr(app_mod, "upsert_file_aggregate", _upsert, raising=True)


# -----------------------------
# Tests
# -----------------------------
def test_health_ok(monkeypatch):
    cap = {}
    _patch_startup_and_db(monkeypatch, capture=cap)
    # Use context manager so startup/shutdown definitely run
    with TestClient(app_mod.app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, dict)
        assert data.get("ok") is True
        # Assert values that reflect startup side effects
        assert data.get("pann_loaded") is True
        assert data.get("sk_pipeline_loaded") in (True, False)
        # DB connection was created
        assert cap.get("conn") is not None

def test_startup_and_shutdown_close_db(monkeypatch):
    cap = {}
    _patch_startup_and_db(monkeypatch, capture=cap)
    # Run inside context to trigger startup+shutdown
    with TestClient(app_mod.app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        # During runtime, connection object is set
        assert cap.get("conn") is not None
        assert cap["conn"].closed is False
    # After shutdown hook ran, global DB_CONN should be None and fake conn closed
    assert app_mod.DB_CONN is None
    assert cap["conn"].closed is True

def test_classify_200_success(monkeypatch):
    cap = {}
    _patch_startup_and_db(monkeypatch, capture=cap)

    # resolve_file_id -> a fixed file_id
    monkeypatch.setattr(app_mod, "resolve_file_id", lambda *a, **k: 42, raising=True)

    # classification core returns a rich dict (with extra fields)
    import classification.scripts.classify as cls
    monkeypatch.setattr(
        cls,
        "run_classification_job",
        lambda **k: {
            "label": "car",
            "probs": {"car": 0.9, "dog": 0.1},
            "pred_prob": 0.9,
            "unknown_threshold": 0.55,
            "is_another": False,
            "num_windows": 5,
            "agg_mode": "mean",
            "processing_ms": 123.0,
        },
        raising=True
    )

    with TestClient(app_mod.app) as client:
        r = client.post("/classify", json={"s3_bucket": "ok", "s3_key": "file.wav", "return_porbs": True})
        assert r.status_code == 200
        body = r.json()
        assert body["label"] == "car"
        # default return_probs is False -> probs stripped
        assert body["probs"] == {"car": 0.9, "dog": 0.1}

    # Verify upsert called with our collected payload
    assert len(cap.get("upserts", [])) == 1
    payload = cap["upserts"][0]["payload"]
    assert payload["file_id"] == 42
    assert payload["head_pred_label"] == "car"
    assert payload["num_windows"] == 5
    assert payload["agg_mode"] == "mean"
    assert payload["processing_ms"] == 123.0

def test_classify_200_with_return_probs_true(monkeypatch):
    cap = {}
    _patch_startup_and_db(monkeypatch, capture=cap)
    monkeypatch.setattr(app_mod, "resolve_file_id", lambda *a, **k: 88, raising=True)

    import classification.scripts.classify as cls
    monkeypatch.setattr(
        cls,
        "run_classification_job",
        lambda **k: {"label": "dog", "probs": {"car": 0.2, "dog": 0.8}},
        raising=True
    )

    with TestClient(app_mod.app) as client:
        r = client.post("/classify", json={"s3_bucket": "b", "s3_key": "key.wav", "return_probs": True})
        assert r.status_code == 200
        body = r.json()
        assert body["label"] == "dog"
        assert body["probs"] == {"car": 0.2, "dog": 0.8}
    # ensure upsert invoked
    assert len(cap.get("upserts", [])) == 1
    assert cap["upserts"][0]["payload"]["file_id"] == 88

def test_classify_404_when_file_missing(monkeypatch):
    cap = {}
    _patch_startup_and_db(monkeypatch, capture=cap)
    # Simulate resolve_file_id failure (file not in public.files)
    def _resolve(*a, **k):
        raise ValueError("not found")
    monkeypatch.setattr(app_mod, "resolve_file_id", _resolve, raising=True)

    with TestClient(app_mod.app) as client:
        r = client.post("/classify", json={"s3_bucket": "b", "s3_key": "missing.wav"})
        assert r.status_code == 404
        # No upsert on failure
        assert cap.get("upserts", []) == []

def test_classify_500_when_core_raises(monkeypatch):
    cap = {}
    _patch_startup_and_db(monkeypatch, capture=cap)
    monkeypatch.setattr(app_mod, "resolve_file_id", lambda *a, **k: 55, raising=True)

    import classification.scripts.classify as cls
    def _raiser(**k):
        raise RuntimeError("boom")
    monkeypatch.setattr(cls, "run_classification_job", _raiser, raising=True)

    with TestClient(app_mod.app) as client:
        r = client.post("/classify", json={"s3_bucket": "b", "s3_key": "crash.wav"})
        assert r.status_code == 500
        # No upsert on failure
        assert cap.get("upserts", []) == []

def test_middleware_executes(monkeypatch):
    """
    Hitting endpoints implicitly passes through the timing middleware.
    This test mainly ensures middleware path executes without errors
    (coverage); assertions are on status only.
    """
    cap = {}
    _patch_startup_and_db(monkeypatch, capture=cap)
    # First pass: just exercise /health
    with TestClient(app_mod.app) as client:
        r1 = client.get("/health")
        assert r1.status_code == 200

    # Second pass: exercise /classify with a minimal classifier mock
    cap = {}
    _patch_startup_and_db(monkeypatch, capture=cap)
    import classification.scripts.classify as cls
    monkeypatch.setattr(cls, "run_classification_job",
                        lambda **k: {"label": "ok", "probs": {}}, raising=True)
    with TestClient(app_mod.app) as client:
        r = client.post("/classify", json={"s3_bucket": "b", "s3_key": "k.wav"})
        assert r.status_code == 200
