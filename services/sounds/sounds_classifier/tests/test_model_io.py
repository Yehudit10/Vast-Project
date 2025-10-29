import numpy as np
from pathlib import Path
import types
import pytest
import soundfile as sf

import classification.core.model_io as mio
from classification.core.model_io import (
    aggregate_matrix,
    segment_waveform,
    load_audio,
    SAMPLE_RATE,
    ensure_checkpoint,
    ensure_numpy_1d,
    _to_numpy,
)

# ---------- aggregate_matrix: happy paths and error branches ----------

def test_aggregate_matrix_mean_and_max_non_empty():
    X = np.array([[0.1, 0.9], [0.7, 0.3], [0.2, 0.8]], dtype=np.float32)
    m = aggregate_matrix(X, mode="mean")
    M = aggregate_matrix(X, mode="max")
    assert np.allclose(m, X.mean(0))
    assert np.allclose(M, X.max(0))

def test_aggregate_matrix_empty_raises():
    X = np.zeros((0, 2), dtype=np.float32)
    with pytest.raises(ValueError) as e:
        aggregate_matrix(X, mode="mean")
    assert "empty window matrix" in str(e.value)

def test_aggregate_matrix_zero_classes_raises():
    X = np.zeros((3, 0), dtype=np.float32)
    with pytest.raises(ValueError) as e:
        aggregate_matrix(X, mode="mean")
    assert "num_classes > 0" in str(e.value)

def test_aggregate_matrix_wrong_type_and_ndim():
    with pytest.raises(TypeError):
        aggregate_matrix([[1, 2], [3, 4]], mode="mean")  # not np.ndarray
    with pytest.raises(ValueError):
        aggregate_matrix(np.array([1, 2, 3], dtype=np.float32), mode="mean")  # 1D
    with pytest.raises(ValueError):
        aggregate_matrix(np.zeros((2, 2, 2), dtype=np.float32), mode="mean")  # 3D

def test_aggregate_matrix_unsupported_mode():
    X = np.ones((2, 2), dtype=np.float32)
    with pytest.raises(ValueError):
        aggregate_matrix(X, mode="median")

def test_aggregate_matrix_nan_and_infs_are_handled():
    X = np.array([[np.nan, 1.0, np.inf, -np.inf],
                  [2.0,   np.nan, 3.0,   -5.0   ]], dtype=np.float32)
    out_mean = aggregate_matrix(X, mode="mean")
    out_max  = aggregate_matrix(X, mode="max")
    assert out_mean.dtype == np.float32
    assert out_max.dtype == np.float32
    # NaNs should be treated as missing, and inf/-inf should be clamped via nan_to_num.
    assert np.isfinite(out_mean).all()
    assert np.isfinite(out_max).all()

# ---------- ensure_numpy_1d & _to_numpy ----------

def test_ensure_numpy_1d_duck_typed_torch_like():
    class DuckTensor:
        def __init__(self, arr): self._arr = np.asarray(arr, dtype=np.float32)
        def detach(self): return self
        def cpu(self): return self
        def numpy(self): return self._arr
    x = DuckTensor([[1.0], [2.0], [3.0]])
    y = ensure_numpy_1d(x)
    assert isinstance(y, np.ndarray)
    assert y.shape == (3,)
    assert y.dtype == np.float32

def test_ensure_numpy_1d_object_with_numpy_method_only():
    class OnlyNumpy:
        def __init__(self, arr): self._arr = np.asarray(arr, dtype=np.float32)
        def numpy(self): return self._arr
    x = OnlyNumpy([[1.0, 2.0, 3.0]])
    y = ensure_numpy_1d(x)
    assert y.shape == (3,)
    assert y.dtype == np.float32

def test__to_numpy_handles_2d_shapes_and_casts_to_float32():
    x = np.array([[1.0], [2.0], [3.0]], dtype=np.float64)
    y = _to_numpy(x)
    assert y.dtype == np.float32
    assert y.shape == (3,)

@pytest.mark.skipif(mio.torch is None, reason="torch is not available")
def test__to_numpy_with_real_torch_tensor_when_available():
    import torch
    x = torch.tensor([[1.0, 2.0, 3.0]], dtype=torch.float32)
    try:
        y = _to_numpy(x)
    except RuntimeError as e:
        # Some builds of torch raise when calling .numpy() if NumPy is mismatched/not present.
        assert "Numpy is not available" in str(e)
    else:
        assert isinstance(y, np.ndarray)
        assert y.dtype == np.float32
        assert y.shape == (3,)

# ---------- segment_waveform edge cases ----------

def test_segment_waveform_empty_and_padding_logic():
    # empty wav returns []
    assert segment_waveform(np.array([], dtype=np.float32), sr=SAMPLE_RATE) == []

    # shorter than one window, pad_last=True adds one padded segment
    short = np.ones(100, dtype=np.float32)
    segs = segment_waveform(short, sr=SAMPLE_RATE, window_sec=0.01, hop_sec=0.005, pad_last=True)
    assert len(segs) >= 1
    for s in segs:
        assert s.ndim == 1 and s.dtype == np.float32

    # shorter than one window, pad_last=False should not add segment
    segs2 = segment_waveform(short, sr=SAMPLE_RATE, window_sec=0.01, hop_sec=0.005, pad_last=False)
    # Depending on rounding, there may be 0 or >0 windows; enforce that no tail padding is added:
    # if the first while loop didn't fit any full window, with pad_last=False we expect 0 segments.
    assert len(segs2) in (0,)

def test_segment_waveform_overlap_and_types():
    wav = np.arange(1000, dtype=np.int16)  # non-float input should be casted
    segs = segment_waveform(wav, sr=1000, window_sec=0.1, hop_sec=0.05, pad_last=True)
    assert len(segs) >= 1
    assert all(s.dtype == np.float32 for s in segs)

# ---------- load_audio: WAV roundtrip & padding ----------

def _sine(sr: int, seconds: float) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False, dtype=np.float32)
    return np.sin(2 * np.pi * 440.0 * t).astype(np.float32)

def test_load_audio_roundtrip_and_padding(tmp_path: Path):
    wav = _sine(SAMPLE_RATE, 0.25)  # shorter than MIN_SAMPLES (16000)
    p = tmp_path / "a.wav"
    sf.write(p, wav, samplerate=SAMPLE_RATE, subtype="PCM_16")
    out = load_audio(str(p), SAMPLE_RATE)
    assert out.dtype == np.float32
    assert out.ndim == 1
    assert out.size >= mio.MIN_SAMPLES  # padded

def test_load_audio_resample_path(monkeypatch, tmp_path: Path):
    # Write at sr=16000; target is 32000. Force librosa.resample path.
    wav16 = _sine(16000, 0.2).astype(np.float32)
    p = tmp_path / "b.wav"
    sf.write(p, wav16, samplerate=16000, subtype="PCM_16")

    called = {"resample": False}
    def fake_resample(y, orig_sr, target_sr):
        called["resample"] = True
        # return float64 to test cast back to float32
        return np.asarray(np.repeat(y, 2), dtype=np.float64)

    monkeypatch.setattr(mio.librosa, "resample", fake_resample, raising=True)
    out = load_audio(str(p), SAMPLE_RATE)
    assert called["resample"] is True
    assert out.dtype == np.float32
    assert out.ndim == 1

# ---------- load_audio: HARD_EXTS (mp3/m4a/...) branch + ffmpeg fallback ----------

def test_load_audio_hard_ext_uses_librosa_success(monkeypatch, tmp_path: Path):
    # Fake an mp3 file; we'll mock librosa.load to return data, so the bytes don't matter.
    p = tmp_path / "x.mp3"
    p.write_bytes(b"ID3")

    def fake_librosa_load(path, sr, mono):
        assert str(path) == str(p)
        return np.ones(100, dtype=np.float32), sr

    monkeypatch.setattr(mio.librosa, "load", fake_librosa_load, raising=True)
    out = load_audio(str(p), SAMPLE_RATE)
    assert out.dtype == np.float32
    assert out.ndim == 1
    assert out.size >= mio.MIN_SAMPLES

def test_load_audio_hard_ext_librosa_fail_ffmpeg_fallback(monkeypatch, tmp_path: Path):
    p = tmp_path / "y.m4a"
    p.write_bytes(b"\x00\x00\x00\x20ftypM4A ")  # header-ish; not used

    def fake_librosa_fail(*a, **k): raise RuntimeError("boom")
    monkeypatch.setattr(mio.librosa, "load", fake_librosa_fail, raising=True)
    monkeypatch.setattr(mio, "has_ffmpeg", lambda: True, raising=True)
    # make ffmpeg path return short buffer to test padding
    monkeypatch.setattr(mio, "decode_with_ffmpeg_to_float32_mono",
                        lambda path, target_sr: np.ones(10, dtype=np.float32), raising=True)
    out = load_audio(str(p), SAMPLE_RATE)
    assert out.size >= mio.MIN_SAMPLES
    assert out.dtype == np.float32

def test_load_audio_all_fail_then_ffmpeg(monkeypatch, tmp_path: Path):
    # For non-HARD ext: raise in soundfile.read, then raise in librosa.load, then use ffmpeg
    p = tmp_path / "z.ogg"
    p.write_bytes(b"OggS...")

    def fake_sf_read(*a, **k): raise RuntimeError("sf fail")
    def fake_librosa_load(*a, **k): raise RuntimeError("librosa fail")

    monkeypatch.setattr(sf, "read", fake_sf_read, raising=True)
    monkeypatch.setattr(mio.librosa, "load", fake_librosa_load, raising=True)
    monkeypatch.setattr(mio, "has_ffmpeg", lambda: True, raising=True)
    monkeypatch.setattr(mio, "decode_with_ffmpeg_to_float32_mono",
                        lambda path, target_sr: np.ones(33, dtype=np.float32), raising=True)
    out = load_audio(str(p), SAMPLE_RATE)
    assert out.ndim == 1 and out.dtype == np.float32

# ---------- ffmpeg helpers ----------

def test_has_ffmpeg_uses_shutil_which(monkeypatch):
    # Ensure function depends on shutil.which
    monkeypatch.setattr(mio.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    assert mio.has_ffmpeg() is True
    monkeypatch.setattr(mio.shutil, "which", lambda _: None)
    assert mio.has_ffmpeg() is False

def test_decode_with_ffmpeg_to_float32_mono_monkeypatched(monkeypatch, tmp_path: Path):
    # We won't call real ffmpeg; we mock subprocess.run to return a small f32 buffer.
    p = tmp_path / "q.ogg"
    p.write_bytes(b"OggS...")

    class DummyProc:
        def __init__(self, data): self.stdout = data; self.stderr = b""
    # 4 float32 numbers -> 16 bytes; MIN_SAMPLES will trigger padding.
    raw = (np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)).tobytes()

    monkeypatch.setattr(
        mio.subprocess, "run",
        lambda cmd, stdout, stderr, check: DummyProc(raw),
        raising=True
    )

    out = mio.decode_with_ffmpeg_to_float32_mono(str(p), mio.SAMPLE_RATE)
    assert out.dtype == np.float32
    assert out.ndim == 1
    assert out.size >= mio.MIN_SAMPLES

# ---------- ensure_checkpoint (patch urllib at global module level) ----------

def test_ensure_checkpoint_downloads_when_missing(monkeypatch, tmp_path):
    target = tmp_path / "models" / "panns_data" / "m.pth"
    called = {"ok": False}
    def fake_urlretrieve(url, dst):
        called["ok"] = True
        Path(dst).write_bytes(b"ok")
    monkeypatch.setattr("urllib.request.urlretrieve", fake_urlretrieve, raising=True)
    path = ensure_checkpoint(str(target), "http://example.com/m.pth")
    assert called["ok"] is True
    assert Path(path).exists()

def test_ensure_numpy_and_to_numpy_helpers():
    x = np.array([[1.0], [2.0], [3.0]], dtype=np.float32)
    assert ensure_numpy_1d(x).shape == (3,)
    y = _to_numpy(x.reshape(1, -1))
    assert y.ndim == 1
