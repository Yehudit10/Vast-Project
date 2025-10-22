import os
import sys
from pathlib import Path

# Robust project root detection:
# - If tests are executed from repo root: parents will include the directory that contains "classification".
# - If tests are executed from inside the 'classification' directory, we still find its parent.
_here = Path(__file__).resolve()
# Walk up parents until we find a directory that contains 'classification' subfolder
proj_root = None
for p in [_here] + list(_here.parents):
    candidate = p / "classification"
    if candidate.exists() and candidate.is_dir():
        proj_root = p
        break

if proj_root is None:
    # Fallback: use two levels up (common layout tests/ inside project)
    proj_root = _here.parents[2]

# Ensure the project root (the parent of 'classification') is on sys.path so
# "import classification..." works regardless of current working dir.
if str(proj_root) not in sys.path:
    sys.path.insert(0, str(proj_root))

# Optionally also add the classification dir itself for direct imports
classification_dir = proj_root / "classification"
if str(classification_dir) not in sys.path:
    sys.path.insert(0, str(classification_dir))

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
    np.random.seed(42)
    yield

@pytest.fixture
def tmp_wav_path(tmp_path: Path) -> Path:
    """
    Create a short stereo WAV (16 kHz, ~0.25s) for audio-loading tests.
    Returns the file path.
    """
    sr = 16000
    t = np.linspace(0, 0.25, int(0.25 * sr), endpoint=False)
    left = 0.1 * np.sin(2 * np.pi * 440 * t)  # 440 Hz sine
    right = 0.1 * np.sin(2 * np.pi * 660 * t)  # 660 Hz sine
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

@pytest.fixture
def mock_head():
    """
    Mock classification head that returns predictable outputs.
    Useful for testing pipeline without loading real models.
    """
    from unittest.mock import Mock
    head = Mock()
    head.predict_proba.return_value = np.array([[0.7, 0.2, 0.1]], dtype=np.float32)
    return head

@pytest.fixture
def test_embeddings():
    """Generate test embeddings for head training/testing"""
    n_samples = 100
    n_features = 128
    n_classes = 3
    
    X = np.random.randn(n_samples, n_features).astype(np.float32)
    y = np.random.randint(0, n_classes, n_samples)
    return X, y

@pytest.fixture
def sample_audio_batch(tmp_path):
    """Create a batch of sample audio files with different classes"""
    classes = ['birds', 'insects', 'vehicle']
    files = []
    sr = 16000
    
    for cls in classes:
        cls_dir = tmp_path / cls
        cls_dir.mkdir()
        
        # Create 2 files per class
        for i in range(2):
            duration = 1.0  # seconds
            t = np.linspace(0, duration, int(sr * duration), endpoint=False)
            freq = 440 * (1 + float(i))  # Different frequencies
            audio = 0.1 * np.sin(2 * np.pi * freq * t)
            wav_path = cls_dir / f"{cls}_{i}.wav"
            sf.write(wav_path, audio, sr)
            files.append(wav_path)
    
    return files, classes

@pytest.fixture
def sample_metadata():
    """Sample metadata for model saving/loading tests"""
    return {
        "embedding_dim": 128,
        "class_order": ["birds", "insects", "vehicle"],
        "head_type": "rf",
        "backbone": "cnn14",
        "train_date": "2025-09-21"
    }

