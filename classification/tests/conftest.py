import os
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf

@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """
    Keep unit tests pure and deterministic:
    - Remove DB/device env vars so tests won't accidentally touch infra.
    - Fix random seed.
    """
    for key in ["DB_URL", "DATABASE_URL", "PGHOST", "PGUSER", "PGPASSWORD", "DEVICE"]:
        if key in os.environ:
            monkeypatch.delenv(key, raising=False)
    np.random.seed(0)
    yield

@pytest.fixture
def tmp_wav_path(tmp_path: Path) -> Path:
    """
    Create a short stereo WAV (16 kHz, ~0.25s) for audio-loading tests.
    Returns the file path.
    """
    sr = 16000
    t = np.linspace(0, 0.25, int(0.25 * sr), endpoint=False)
    left = 0.1 * np.sin(2 * np.pi * 440 * t)
    right = 0.1 * np.sin(2 * np.pi * 660 * t)
    stereo = np.stack([left, right], axis=1).astype(np.float32)
    p = tmp_path / "test.wav"
    sf.write(p, stereo, sr)
    return p

@pytest.fixture
def dummy_at_with_dict():
    """
    Dummy 'AudioTagging'-like object that returns a DICT from inference().
    Useful to test parsing paths in model_io.run_* functions without heavy models.
    """
    class Dummy:
        def __init__(self):
            self.labels = ["ignored"]
        def inference(self, wav):
            clip = np.array([0.2, 0.8, np.nan], dtype=np.float32)               # include NaN to test sanitization
            emb  = np.array([[1.0, np.inf, -np.inf]], dtype=np.float32)         # 1x3 with infs (will be sanitized)
            labels = ["dog", "engine", "shotgun"]
            return {"clipwise_output": clip, "embedding": emb, "labels": labels}
    return Dummy()

@pytest.fixture
def dummy_at_with_tuple():
    """
    Dummy 'AudioTagging'-like object that returns a TUPLE from inference().
    Labels=None triggers fallback logic in run_inference (at.labels or class_{i}).
    """
    class Dummy:
        def inference(self, wav):
            clip = np.array([[0.5], [0.1], [0.3]], dtype=np.float32)  # 3x1 -> should be flattened to (3,)
            emb  = np.array([9.0, 8.0, 7.0], dtype=np.float32)
            labels = None
            return (clip, emb, labels)
    return Dummy()
