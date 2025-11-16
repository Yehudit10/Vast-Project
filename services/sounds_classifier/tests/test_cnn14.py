import numpy as np
import types
import builtins
import pytest
import classification.backbones.cnn14 as cnn14
from classification.backbones.cnn14 import run_cnn14_embeddings_batch
from classification.core.model_io import segment_waveform_2d_view, SAMPLE_RATE

class DummyAT:
    def __init__(self, checkpoint_path: str, device: str = "cpu"):
        self.checkpoint_path = checkpoint_path
        self.device = device
    def inference(self, wav):
        # Return (dummy_probs, dummy_embedding)
        emb = np.ones((1, 2048), dtype=np.float32)
        return (None, emb)

class DummyATTuple:
    def inference(self, x):
        # x: (N, samples)
        N = x.shape[0]
        emb_dim = 8
        scores = np.zeros((N, 10), dtype=np.float32)  # unused
        embs = np.arange(N * emb_dim, dtype=np.float32).reshape(N, emb_dim)
        return (scores, embs)

class DummyATDict:
    def inference(self, x):
        N = x.shape[0]
        emb_dim = 16
        return {"embedding": np.ones((N, emb_dim), dtype=np.float32)}
    
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


def test_run_cnn14_embeddings_batch_tuple_output(monkeypatch):
    model = DummyATTuple()
    # Prevent flattening of (N, D) to (N*D,)
    monkeypatch.setattr(cnn14, "_to_numpy",
                        lambda x: np.asarray(x, dtype=np.float32),
                        raising=True)
    
    windows = np.ones((5, 32000), dtype=np.float32)
    E = run_cnn14_embeddings_batch(model, windows, batch_size=2)
    assert E.shape == (5, 8)
    assert np.allclose(E[1], np.arange(8, 16, dtype=np.float32))

def test_run_cnn14_embeddings_batch_dict_output(monkeypatch):
    model = DummyATDict()
    # Prevent flattening of (N, D) to (N*D,)
    monkeypatch.setattr(cnn14, "_to_numpy",
                        lambda x: np.asarray(x, dtype=np.float32),
                        raising=True)
    windows = np.ones((3, 16000), dtype=np.float32)
    E = run_cnn14_embeddings_batch(model, windows, batch_size=32)
    assert E.shape == (3, 16)
    assert np.allclose(E, 1.0)

def test_segment_waveform_2d_basic_exact_fit():
    sr = SAMPLE_RATE
    win_s = 1.0
    hop_s = 0.75
    wav = np.ones(int(sr * 1.6), dtype=np.float32)
    segs = segment_waveform_2d_view(wav, sr=sr, window_sec=win_s, hop_sec=hop_s, pad_last=False)
    # Expect exactly one full window: [0..1.0]
    assert segs.shape[0] == 1
    assert segs.shape[1] == int(sr * win_s)
    # No padding is expected when pad_last=False

def test_segment_waveform_2d_pad_last():
    sr = SAMPLE_RATE
    win_s = 1.0
    hop_s = 0.75
    wav = np.ones(int(sr * 1.6), dtype=np.float32)
    segs = segment_waveform_2d_view(wav, sr=sr, window_sec=win_s, hop_sec=hop_s, pad_last=True)
    # Expect one full window + one padded tail window → total 2
    assert segs.shape[0] == 2
    assert segs.shape[1] == int(sr * win_s)
    assert np.any(segs[-1] == 0.0)

def test_segment_waveform_2d_empty_input_returns_empty_or_padded():
    sr = SAMPLE_RATE
    segs_no_pad = segment_waveform_2d_view(np.zeros(0, dtype=np.float32), sr=sr,
                                           window_sec=1.0, hop_sec=0.5, pad_last=False)
    assert segs_no_pad.shape == (0, int(sr * 1.0))
    segs_pad = segment_waveform_2d_view(np.zeros(0, dtype=np.float32), sr=sr,
                                        window_sec=1.0, hop_sec=0.5, pad_last=True)
    # Current impl returns 0 windows even with pad_last for empty input
    assert segs_pad.shape == (0, int(sr * 1.0))
