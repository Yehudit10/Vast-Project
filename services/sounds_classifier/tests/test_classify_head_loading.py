import json
import numpy as np
import classification.scripts.classify as c


def _reset_runtime():
    c.R = c._Runtime()


def test__load_backbone_once_calls_loader(monkeypatch):
    _reset_runtime()
    old = c.BACKBONE
    try:
        c.BACKBONE = "cnn14"
        called = {"ok": False}
        def fake_loader(checkpoint_path=None, device="cpu", checkpoint_url=None):
            called["ok"] = True
            return object()
        monkeypatch.setattr(c, "load_cnn14_model", fake_loader, raising=True)
        c._load_backbone_once()
        assert called["ok"] is True and c.R.model is not None
        # Second call should be a no-op
        called["ok"] = False
        c._load_backbone_once()
        assert called["ok"] is False
    finally:
        c.BACKBONE = old


def test__load_backbone_once_rejects_non_cnn14():
    _reset_runtime()
    old = c.BACKBONE
    try:
        c.BACKBONE = "something-else"
        try:
            c._load_backbone_once()
            assert False, "Expected RuntimeError for unsupported backbone"
        except RuntimeError as e:
            assert "Only BACKBONE=cnn14" in str(e)
    finally:
        c.BACKBONE = old


def test__load_head_once_requires_head():
    _reset_runtime()
    old = c.HEAD_PATH
    try:
        c.HEAD_PATH = ""
        try:
            c._load_head_once()
            assert False, "Expected RuntimeError when HEAD env/path is missing"
        except RuntimeError as e:
            assert "HEAD env var is required" in str(e)
    finally:
        c.HEAD_PATH = old


def test__load_head_once_uses_labels_csv(monkeypatch):
    _reset_runtime()

    class DummyHead:
        def __init__(self):
            self.classes_ = ["x", "y"]
        def predict_proba(self, X):
            return np.zeros((X.shape[0], 2), dtype=np.float32)

    c.HEAD_PATH = "dummy.joblib"
    monkeypatch.setattr(c.joblib, "load", lambda _: DummyHead(), raising=True)

    monkeypatch.setenv("LABELS_CSV", "labels.csv")
    import classification.core.model_io as mio
    # Important: raising=False because the attribute doesn't exist in the real module
    monkeypatch.setattr(mio, "load_labels_from_csv", lambda _: ["car", "dog"], raising=False)

    c._load_head_once()
    assert c.R.head is not None
    assert c.R.classes == ["car", "dog"]
    monkeypatch.delenv("LABELS_CSV", raising=False)


def test__load_head_once_fallback_to_head_classes(monkeypatch):
    _reset_runtime()

    class DummyHead:
        def __init__(self):
            self.classes_ = ["cat", "plane"]
        def predict_proba(self, X):
            return np.zeros((X.shape[0], 2), dtype=np.float32)

    c.HEAD_PATH = "dummy.joblib"
    monkeypatch.setattr(c.joblib, "load", lambda _: DummyHead(), raising=True)
    monkeypatch.delenv("LABELS_CSV", raising=False)
    monkeypatch.setenv("HEAD_META", "does_not_exist.json")

    c._load_head_once()
    assert c.R.head is not None
    assert c.R.classes == ["cat", "plane"]


def test__load_head_once_uses_meta_with_indexed_classes(monkeypatch, tmp_path):
    _reset_runtime()

    class DummyHeadInt:
        def __init__(self):
            self.classes_ = [0, 1]
        def predict_proba(self, X):
            return np.zeros((X.shape[0], 2), dtype=np.float32)

    c.HEAD_PATH = "dummy.joblib"
    monkeypatch.setattr(c.joblib, "load", lambda _: DummyHeadInt(), raising=True)

    meta_path = tmp_path / "head_meta.json"
    meta_path.write_text(json.dumps({"class_order": ["engine", "bird"]}), encoding="utf-8")
    monkeypatch.setenv("HEAD_META", str(meta_path))
    monkeypatch.delenv("LABELS_CSV", raising=False)

    c._load_head_once()
    assert c.R.classes == ["engine", "bird"]


def test__load_head_once_meta_length_mismatch_raises(monkeypatch, tmp_path):
    _reset_runtime()

    class DummyHeadInt:
        def __init__(self):
            self.classes_ = [0, 1]
        def predict_proba(self, X):
            return np.zeros((X.shape[0], 2), dtype=np.float32)

    c.HEAD_PATH = "dummy.joblib"
    monkeypatch.setattr(c.joblib, "load", lambda _: DummyHeadInt(), raising=True)

    meta_path = tmp_path / "bad_meta.json"
    meta_path.write_text(json.dumps({"class_order": ["only-one"]}), encoding="utf-8")
    monkeypatch.setenv("HEAD_META", str(meta_path))
    monkeypatch.delenv("LABELS_CSV", raising=False)

    try:
        c._load_head_once()
        assert False, "Expected RuntimeError for meta length mismatch"
    except RuntimeError as e:
        assert "class_order length" in str(e)
