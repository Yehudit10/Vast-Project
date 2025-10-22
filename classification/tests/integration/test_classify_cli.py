import pytest
import numpy as np
from pathlib import Path

# --------------------------
# Dummy classes and functions
# --------------------------
class DummyModel:
    def __init__(self, device="cpu"):
        self.device = device

    def forward(self, x):
        return np.zeros((len(x), 10))  # dummy output for 10 classes

class DummyAudioTagging:
    def __init__(self, *args, **kwargs):
        pass

    def run(self, *args, **kwargs):
        return {"preds": np.zeros(10)}

# --------------------------
# Auto patching fixture
# --------------------------
@pytest.fixture(autouse=True)
def patch_all(monkeypatch):
    # Patch CNN14 loader
    import backbones.cnn14 as cnn14
    monkeypatch.setattr(
        cnn14,
        "load_cnn14_model",
        lambda checkpoint, checkpoint_url=None, device="cpu": DummyModel(device=device),
    )

    # Patch classify module functions to avoid real AudioTagging / heavy computations
    import scripts.classify as classify

    # Patch functions that would call real models or I/O
    monkeypatch.setattr(classify, "run_inference", lambda *a, **k: np.zeros(10))
    monkeypatch.setattr(classify, "run_inference_with_embedding", lambda *a, **k: np.zeros(10))
    monkeypatch.setattr(classify, "aggregate_matrix", lambda *a, **k: np.zeros(10))
    monkeypatch.setattr(classify, "load_audio", lambda *a, **k: np.zeros(16000))  # 1 sec dummy audio
    monkeypatch.setattr(classify, "segment_waveform", lambda *a, **k: [np.zeros(16000)])

# --------------------------
# Tests
# --------------------------
def test_classify_cli(tmp_path):
    import scripts.classify as classify

    # prepare dummy audio file path
    audio_file = tmp_path / "dummy.wav"
    audio_file.write_bytes(b"dummy")

    # call main classify function (simulate CLI)
    result = classify.run_inference(audio_file)
    
    # assert it returns the dummy array
    assert isinstance(result, np.ndarray)
    assert result.shape[0] == 10  # matches DummyModel output

def test_classify_cli_with_embedding(tmp_path):
    import scripts.classify as classify

    # prepare dummy audio file path
    audio_file = tmp_path / "dummy.wav"
    audio_file.write_bytes(b"dummy")

    # call main classify function with embedding
    result = classify.run_inference_with_embedding(audio_file)

    # assert it returns the dummy array
    assert isinstance(result, np.ndarray)
    assert result.shape[0] == 10
