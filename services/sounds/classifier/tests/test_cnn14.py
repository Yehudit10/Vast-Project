import numpy as np
import types
import builtins
import pytest

import classification.backbones.cnn14 as cnn14

class DummyAT:
    def __init__(self, checkpoint_path: str, device: str = "cpu"):
        self.checkpoint_path = checkpoint_path
        self.device = device
    def inference(self, wav):
        # Return (dummy_probs, dummy_embedding)
        emb = np.ones((1, 2048), dtype=np.float32)
        return (None, emb)

def test_load_cnn14_model_uses_ensure_checkpoint(monkeypatch, tmp_path):
    ckpt = tmp_path / "m.pth"
    def fake_ensure(path, url):
        ckpt.write_bytes(b"dummy")
        return str(ckpt)
    monkeypatch.setattr(cnn14, "ensure_checkpoint", fake_ensure)
    # Mock panns_inference.AudioTagging
    monkeypatch.setattr(cnn14, "AudioTagging", DummyAT, raising=True)

    m = cnn14.load_cnn14_model(checkpoint_path=str(ckpt), device="cpu")
    assert isinstance(m, DummyAT)
    assert m.checkpoint_path == str(ckpt)

def test_run_cnn14_embedding_happy_path(monkeypatch):
    dummy = DummyAT("x")
    x = np.random.randn(32000).astype(np.float32)
    e = cnn14.run_cnn14_embedding(dummy, x)
    assert e.shape == (2048,)

def test_run_cnn14_embedding_empty_raises(monkeypatch):
    dummy = DummyAT("x")
    with pytest.raises(ValueError):
        cnn14.run_cnn14_embedding(dummy, np.array([], dtype=np.float32))
