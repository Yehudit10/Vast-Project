import numpy as np
from pathlib import Path
import classification.scripts.classify as c


# ---- Helpers ----
class DummyHead:
    def __init__(self, classes):
        self.classes_ = classes
        self._probas = None
    def set_out(self, arr):
        self._probas = arr
    def predict_proba(self, X):
        n = X.shape[0]
        return np.tile(self._probas, (n, 1))

def _reset_runtime():
    c.R = c._Runtime()

def _to_dict_result(res):
    """Normalize classifier outputs to a dict {label, probs} for tests."""
    if isinstance(res, tuple):
        label, probs = res
        return {"label": label, "probs": probs}
    return res


# ---- Core classification flow & validations ----
def test_classify_file_unknown_threshold(monkeypatch):
    _reset_runtime()
    c.R.model = object()
    head = DummyHead(classes=["car", "dog"])
    head.set_out(np.array([0.51, 0.49], dtype=np.float32))  # may fall under UNKNOWN_THRESHOLD
    c.R.head = head
    c.R.classes = head.classes_

    monkeypatch.setattr(c, "load_audio", lambda p, sr: np.ones(16000, dtype=np.float32), raising=True)
    monkeypatch.setattr(c, "segment_waveform", lambda *a, **k: [np.ones(16000, dtype=np.float32)], raising=True)
    monkeypatch.setattr(c, "run_cnn14_embedding", lambda m, w: np.array([1, 2, 3, 4], dtype=np.float32), raising=True)

    result = _to_dict_result(c.classify_file("dummy.wav"))
    assert result["label"] in ("car", "another")
    assert set(result["probs"].keys()) == {"car", "dog"}


def test__aggregate_probs_rejects_bad_ndim():
    x = np.array([0.1, 0.9], dtype=np.float32)  # 1-D
    try:
        c._aggregate_probs(x)
        assert False, "Expected ValueError for 1-D array"
    except ValueError as e:
        assert "expected shape" in str(e)


def test__aggregate_probs_empty_windows_returns_zeros():
    x = np.zeros((0, 3), dtype=np.float32)
    out = c._aggregate_probs(x)
    assert out.shape == (3,)
    assert np.allclose(out, 0.0)


def test_classify_file_returns_another_when_no_segments(monkeypatch):
    _reset_runtime()
    c.R.model = object()
    class Head:
        def __init__(self): self.classes_ = ["car", "dog"]
        def predict_proba(self, X): return np.zeros((X.shape[0], 2), dtype=np.float32)
    c.R.head = Head()
    c.R.classes = ["car", "dog"]

    monkeypatch.setattr(c, "load_audio", lambda p, sr: np.ones(16000, dtype=np.float32), raising=True)
    monkeypatch.setattr(c, "segment_waveform", lambda *a, **k: [], raising=True)
    monkeypatch.setattr(c, "run_cnn14_embedding", lambda m, w: np.array([1, 2, 3, 4], dtype=np.float32), raising=True)

    result = _to_dict_result(c.classify_file("dummy.wav"))
    assert result["label"] == "another"
    assert set(result["probs"].keys()) == {"car", "dog"}


def test_classify_file_with_agg_max(monkeypatch):
    _reset_runtime()
    old_agg = c.AGG
    c.AGG = "max"
    try:
        c.R.model = object()
        class Head:
            def __init__(self): self.classes_ = ["a", "b"]
            def predict_proba(self, X):
                return np.array([[0.2, 0.8], [0.6, 0.4]], dtype=np.float32)
        c.R.head = Head()
        c.R.classes = ["a", "b"]

        monkeypatch.setattr(c, "load_audio", lambda p, sr: np.ones(2 * 16000, dtype=np.float32), raising=True)
        monkeypatch.setattr(
            c,
            "segment_waveform",
            lambda *a, **k: [np.ones(16000, dtype=np.float32), np.ones(16000, dtype=np.float32)],
            raising=True
        )
        monkeypatch.setattr(c, "run_cnn14_embedding", lambda m, w: np.array([1, 2, 3, 4], dtype=np.float32), raising=True)

        result = _to_dict_result(c.classify_file("x.wav"))
        assert set(result["probs"].keys()) == {"a", "b"}
        assert np.isclose(result["probs"]["a"], 0.6) or np.isclose(result["probs"]["b"], 0.8)
    finally:
        c.AGG = old_agg


def test_run_classification_job_happy_path(monkeypatch, tmp_path):
    _reset_runtime()
    # MinIO client mock
    class Stat: size = 10; content_type = "audio/wav"
    class Client:
        def stat_object(self, b, k): return Stat()
        def fget_object(self, b, k, dst): Path(dst).write_bytes(b"RIFF")
    monkeypatch.setattr(c, "Minio", lambda *a, **k: Client(), raising=True)

    c.WRITE_DB, c.DB_URL = False, ""
    c.KAFKA_BROKERS, c.ALERTS_TOPIC = "", "dev-robot-alerts"
    monkeypatch.setattr(c.alerts, "send_alert", lambda **kw: None, raising=True)

    c.R.model = object()
    head = DummyHead(classes=["car", "dog"]); head.set_out(np.array([0.6, 0.4], dtype=np.float32))
    c.R.head = head; c.R.classes = head.classes_

    monkeypatch.setattr(c, "load_audio", lambda p, sr: np.ones(16000, dtype=np.float32), raising=True)
    monkeypatch.setattr(c, "segment_waveform", lambda *a, **k: [np.ones(16000, dtype=np.float32)], raising=True)
    monkeypatch.setattr(c, "run_cnn14_embedding", lambda m, w: np.array([1, 2, 3, 4], dtype=np.float32), raising=True)

    out = _to_dict_result(c.run_classification_job(s3_bucket="b", s3_key="k.wav"))
    assert out["label"] in ("car", "another")
    assert "probs" in out and isinstance(out["probs"], dict)


def test_run_classification_job_bucket_not_allowed():
    _reset_runtime()
    c.R.head = object()
    old = c.ALLOWED_BUCKETS
    c.ALLOWED_BUCKETS = ["only-this-bucket"]
    try:
        try:
            _ = c.run_classification_job(s3_bucket="not-allowed", s3_key="a.wav")
            assert False, "Expected RuntimeError for disallowed bucket"
        except RuntimeError as e:
            assert "not allowed" in str(e)
    finally:
        c.ALLOWED_BUCKETS = old


def test_run_classification_job_rejects_content_type(monkeypatch):
    _reset_runtime()
    c.R.head = object()
    c.ALLOWED_BUCKETS = []
    old_types = c.ALLOWED_CONTENT_TYPES
    c.ALLOWED_CONTENT_TYPES = ["audio/wav"]

    class Stat: size = 1024; content_type = "text/plain"
    class Client:
        def stat_object(self, b, k): return Stat()
        def fget_object(self, b, k, dst): Path(dst).write_bytes(b"RIFF")
    monkeypatch.setattr(c, "Minio", lambda *a, **k: Client(), raising=True)

    try:
        _ = c.run_classification_job(s3_bucket="ok", s3_key="a.wav")
        assert False, "Expected RuntimeError for unsupported content-type"
    except RuntimeError as e:
        assert "Unsupported content-type" in str(e)
    finally:
        c.ALLOWED_CONTENT_TYPES = old_types


def test_run_classification_job_rejects_size(monkeypatch):
    _reset_runtime()
    c.R.head = object()
    c.ALLOWED_BUCKETS = []
    old_max = c.MAX_BYTES; c.MAX_BYTES = 10
    class Stat: size = 11; content_type = "audio/wav"
    class Client:
        def stat_object(self, b, k): return Stat()
        def fget_object(self, b, k, dst): Path(dst).write_bytes(b"RIFF")
    monkeypatch.setattr(c, "Minio", lambda *a, **k: Client(), raising=True)

    try:
        _ = c.run_classification_job(s3_bucket="ok", s3_key="a.wav")
        assert False, "Expected RuntimeError for object too large"
    except RuntimeError as e:
        assert "Object too large" in str(e)
    finally:
        c.MAX_BYTES = old_max


def test_run_classification_job_s3error_fails_fast(monkeypatch):
    _reset_runtime()
    c.R.head = object()
    c.ALLOWED_BUCKETS = []

    class S3Err(Exception): pass
    monkeypatch.setattr(c, "S3Error", S3Err, raising=True)
    class Client:
        def stat_object(self, b, k): raise S3Err("boom")
        def fget_object(self, b, k, dst): raise AssertionError("should not be called")
    monkeypatch.setattr(c, "Minio", lambda *a, **k: Client(), raising=True)

    try:
        _ = c.run_classification_job(s3_bucket="ok", s3_key="a.wav")
        assert False, "Expected RuntimeError wrapping S3 failure"
    except RuntimeError as e:
        assert "S3 stat failed" in str(e)


def test_run_classification_job_adds_wav_suffix_when_missing(monkeypatch):
    _reset_runtime()
    c.R.head = object()
    c.R.classes = ["car", "dog"]
    c.ALLOWED_BUCKETS = []

    class Stat: size = 100; content_type = "audio/wav"
    observed = {"ext": None}
    class Client:
        def stat_object(self, b, k): return Stat()
        def fget_object(self, b, k, dst):
            observed["ext"] = Path(dst).suffix
            Path(dst).write_bytes(b"RIFF")
    monkeypatch.setattr(c, "Minio", lambda *a, **k: Client(), raising=True)
    monkeypatch.setattr(c, "classify_file", lambda p, **_: {"label": "another", "probs": {"car": 0.0, "dog": 0.0}}, raising=True)
    monkeypatch.setattr(c.os, "remove", lambda p: None, raising=True)

    out = _to_dict_result(c.run_classification_job(s3_bucket="ok", s3_key="noext"))
    assert out["label"] in ("another", "car", "dog")
    assert observed["ext"] == ".wav"
