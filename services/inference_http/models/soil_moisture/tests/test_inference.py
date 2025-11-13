import sys
import types
import numpy as np
from PIL import Image

# Pre-inject a lightweight stub for app.onnx_model to avoid importing onnxruntime
stub_mod = types.ModuleType("app.onnx_model")
class _StubONNX:
    def __init__(self, *a, **k):
        # minimal surface to satisfy Inferencer init
        self.label_map = {"0": "dry", "1": "wet"}
    def predict_proba_patch(self, patch):
        return np.array([0.5, 0.5], dtype=float)
stub_mod.ONNXMoistureModel = _StubONNX
sys.modules.setdefault("app.onnx_model", stub_mod)

from app.config import Settings
from app import inference as infmod


class _FakeDryModel:
    def __init__(self, *args, **kwargs):
        # emulates label_map: index->label
        self.label_map = {"0": "dry", "1": "wet"}

    def predict_proba_patch(self, patch):
        # Always predict class 0 (dry) with high confidence
        return np.array([0.9, 0.1], dtype=float)


class _FakeWetModel:
    def __init__(self, *args, **kwargs):
        self.label_map = {"0": "dry", "1": "wet"}

    def predict_proba_patch(self, patch):
        # Always predict class 1 (wet)
        return np.array([0.1, 0.9], dtype=float)


def _make_inferencer(monkeypatch, model_cls):
    # Replace ONNX model with a lightweight fake
    monkeypatch.setattr(infmod, "ONNXMoistureModel", lambda *a, **k: model_cls())

    s = Settings()
    s.patch_size = 10
    s.patch_stride = 10
    s.decision_window_sec = 300
    return infmod.Inferencer(s)


def _make_image(w=20, h=10):
    return Image.new("RGB", (w, h), color=(128, 128, 128))


def test_decision_run_when_dry_ratio_high(monkeypatch):
    inf = _make_inferencer(monkeypatch, _FakeDryModel)
    # 20x10 with 10x10 patches & stride 10 => 2 patches
    img = _make_image(20, 10)
    zone_cfg = {"_state": "stop", "dry_ratio_high": 0.5, "dry_ratio_low": 0.3, "min_patches": 2, "duration_min": 7}

    result, debug = inf.infer_image(img, zone_cfg)
    assert result["patch_count"] == 2
    assert result["dry_ratio"] == 1.0
    assert result["decision"] == "run"
    assert zone_cfg["_state"] == "run"


def test_decision_stop_when_dry_ratio_low_and_prev_run(monkeypatch):
    inf = _make_inferencer(monkeypatch, _FakeWetModel)
    img = _make_image(20, 10)  # 2 patches
    zone_cfg = {"_state": "run", "dry_ratio_high": 0.6, "dry_ratio_low": 0.25, "min_patches": 2, "duration_min": 5}

    result, _ = inf.infer_image(img, zone_cfg)
    assert result["patch_count"] == 2
    assert result["dry_ratio"] == 0.0
    assert result["decision"] == "stop"
    assert zone_cfg["_state"] == "stop"


def test_noop_when_not_enough_patches(monkeypatch):
    inf = _make_inferencer(monkeypatch, _FakeDryModel)
    img = _make_image(20, 10)  # 2 patches
    zone_cfg = {"_state": "stop", "dry_ratio_high": 0.5, "dry_ratio_low": 0.3, "min_patches": 3, "duration_min": 7}

    result, _ = inf.infer_image(img, zone_cfg)
    assert result["patch_count"] == 2
    assert result["decision"] == "noop"
    # State remains unchanged
    assert zone_cfg["_state"] == "stop"


def test_decision_window_bucket_rounds_down(monkeypatch):
    inf = _make_inferencer(monkeypatch, _FakeDryModel)
    # With window 300s, 1234 -> bucket start 1200
    bucket = inf.decision_window_bucket(1234.0)
    assert bucket == 1200
