"""
Unit tests for core/model_io.py

This suite focuses on pure / near-pure functions, using lightweight mocks instead
of real ffmpeg/network/heavy models. Each test includes a short docstring to clarify intent.
"""

import numpy as np
import pytest
import soundfile as sf
from pathlib import Path

# Import under test (assumes running pytest from classification/)
from core import model_io


# ---------- has_ffmpeg ----------

def test_has_ffmpeg_true(monkeypatch):
    """has_ffmpeg returns True when shutil.which finds ffmpeg."""
    monkeypatch.setattr(model_io.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    assert model_io.has_ffmpeg() is True


def test_has_ffmpeg_false(monkeypatch):
    """has_ffmpeg returns False when ffmpeg is not found."""
    monkeypatch.setattr(model_io.shutil, "which", lambda _: None)
    assert model_io.has_ffmpeg() is False


# ---------- decode_with_ffmpeg_to_float32_mono ----------

def test_decode_with_ffmpeg_to_float32_mono_basic(monkeypatch):
    """
    Mock subprocess.run only for ffmpeg; delegate to real run for anything else
    (so numpy.testing etc. won't break). Expect padding to MIN_SAMPLES.
    """
    samples = np.array([0.0, 0.5, -0.5, 1.0], dtype=np.float32)
    fake_stdout = samples.tobytes()

    class FakeProc:
        def __init__(self):
            self.stdout = fake_stdout
            self.stderr = b""

    import subprocess as _sp
    real_run = _sp.run

    def fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and "ffmpeg" in str(cmd[0]).lower():
            return FakeProc()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(model_io.subprocess, "run", fake_run)
    out = model_io.decode_with_ffmpeg_to_float32_mono("/some/file.mp3", target_sr=model_io.SAMPLE_RATE)
    assert out.dtype == np.float32
    # length should be padded to at least MIN_SAMPLES
    assert len(out) >= model_io.MIN_SAMPLES
    # first samples match our fake payload
    np.testing.assert_array_equal(out[: len(samples)], samples)
    # the rest is zero padding
    if len(out) > len(samples):
        assert np.all(out[len(samples):] == 0.0)


def test_decode_with_ffmpeg_to_float32_mono_pads(monkeypatch):
    """
    If ffmpeg returns fewer than MIN_SAMPLES, function pads with zeros.
    """
    tiny = np.array([0.1], dtype=np.float32)

    class FakeProc:
        def __init__(self): self.stdout = tiny.tobytes(); self.stderr = b""

    monkeypatch.setattr(model_io.subprocess, "run", lambda *a, **k: FakeProc())
    out = model_io.decode_with_ffmpeg_to_float32_mono("/p.mp3", target_sr=model_io.SAMPLE_RATE)
    assert out.dtype == np.float32
    assert out.shape[0] >= model_io.MIN_SAMPLES
    assert np.allclose(out[0], 0.1)


# ---------- ensure_checkpoint ----------

def test_ensure_checkpoint_existing(tmp_path: Path):
    """Existing checkpoint returns immediately without download."""
    p = tmp_path / "ckpt" / "m.ckpt"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    out = model_io.ensure_checkpoint(str(p), checkpoint_url=None)
    assert out == str(p)


def test_ensure_checkpoint_missing_no_url(tmp_path: Path):
    """Missing checkpoint and no URL -> FileNotFoundError."""
    p = tmp_path / "ckpt" / "m.ckpt"
    with pytest.raises(FileNotFoundError):
        model_io.ensure_checkpoint(str(p), checkpoint_url=None)


def test_ensure_checkpoint_downloads(monkeypatch, tmp_path: Path):
    """Missing checkpoint + URL -> urlretrieve is called and file appears."""
    p = tmp_path / "ckpt" / "m.ckpt"

    def fake_urlretrieve(url, dst):
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        Path(dst).write_bytes(b"OK")
        return (str(dst), None)

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)
    out = model_io.ensure_checkpoint(str(p), checkpoint_url="http://example/ckpt.bin")
    assert Path(out).exists()
    assert Path(out).read_bytes() == b"OK"


# ---------- load_audio ----------

def test_load_audio_wav_stereo_to_mono_and_resample(tmp_path: Path):
    """
    WAV path: read via soundfile, mix stereo->mono, cast to float32 and resample if needed.
    Here we write a 0.25s stereo @16kHz and target 32kHz -> length roughly doubles.
    """
    # Create stereo 16kHz wav
    sr = 16000
    t = np.linspace(0, 0.25, int(0.25 * sr), endpoint=False)
    left = 0.1 * np.sin(2 * np.pi * 440 * t)
    right = 0.1 * np.sin(2 * np.pi * 660 * t)
    stereo = np.stack([left, right], axis=1).astype(np.float32)
    p = tmp_path / "test.wav"
    sf.write(p, stereo, sr)

    y = model_io.load_audio(str(p), target_sr=model_io.SAMPLE_RATE)
    assert y.ndim == 1 and y.dtype == np.float32
    # Allow internal padding to MIN_SAMPLES
    assert len(y) >= int(0.1 * model_io.SAMPLE_RATE)
    assert len(y) >= model_io.MIN_SAMPLES


def test_load_audio_compressed_first_librosa(monkeypatch, tmp_path: Path):
    """
    For compressed extensions (e.g., .mp3), function tries librosa.load first.
    Implementation pads short clips up to MIN_SAMPLES.
    """
    p = tmp_path / "fake.mp3"
    p.write_bytes(b"not_mp3")

    def fake_librosa_load(path, sr, mono):
        assert Path(path) == p and sr == model_io.SAMPLE_RATE and mono is True
        t = np.linspace(0, 0.1, int(0.1 * sr), endpoint=False)
        return np.sin(2 * np.pi * 220 * t).astype(np.float32), sr

    monkeypatch.setattr(model_io.librosa, "load", fake_librosa_load)
    y = model_io.load_audio(str(p), target_sr=model_io.SAMPLE_RATE)
    assert y.ndim == 1 and y.dtype == np.float32

    expected_len = int(0.1 * model_io.SAMPLE_RATE)  # raw librosa length
    # allow internal padding up to MIN_SAMPLES
    assert len(y) >= expected_len
    assert len(y) >= model_io.MIN_SAMPLES

    # first expected_len samples equal to the synthetic sine
    t = np.linspace(0, 0.1, expected_len, endpoint=False)
    expected = np.sin(2 * np.pi * 220 * t).astype(np.float32)
    np.testing.assert_allclose(y[:expected_len], expected, rtol=1e-6, atol=1e-6)

    # the rest is zero padding
    if len(y) > expected_len:
        assert np.all(y[expected_len:] == 0.0)


def test_load_audio_compressed_fallback_ffmpeg(monkeypatch, tmp_path: Path):
    """
    If librosa.load fails, loader should fallback to ffmpeg WHEN available.
    """
    p = tmp_path / "x.opus"
    p.write_bytes(b"not_opus")

    def fake_librosa_load(*args, **kwargs):
        raise RuntimeError("simulated librosa failure")

    monkeypatch.setattr(model_io.librosa, "load", fake_librosa_load)
    monkeypatch.setattr(model_io, "has_ffmpeg", lambda: True)
    monkeypatch.setattr(model_io, "decode_with_ffmpeg_to_float32_mono",
                        lambda path, target_sr: np.array([1, 2, 3], dtype=np.float32))
    y = model_io.load_audio(str(p), target_sr=model_io.SAMPLE_RATE)
    np.testing.assert_array_equal(y[:3], np.array([1, 2, 3], dtype=np.float32))


def test_load_audio_total_failure_raises(monkeypatch, tmp_path: Path):
    """
    If soundfile & librosa fail and ffmpeg is unavailable, the loader raises.
    """
    p = tmp_path / "bad.wav"
    p.write_bytes(b"garbage")

    monkeypatch.setattr(model_io.sf, "read", lambda *a, **k: (_raise(RuntimeError("sf fail")), None))
    monkeypatch.setattr(model_io.librosa, "load", lambda *a, **k: _raise(RuntimeError("librosa fail")))
    monkeypatch.setattr(model_io, "has_ffmpeg", lambda: False)

    with pytest.raises(Exception):
        model_io.load_audio(str(p), target_sr=model_io.SAMPLE_RATE)


def _raise(err):
    raise err


# ---------- _to_numpy ----------

def test_to_numpy_flattens_and_dtype():
    """
    _to_numpy returns float32 1-D arrays, flattening 2-D 1xN or Nx1 and lists.
    """
    x1 = np.array([[1.0, 2.0, 3.0]], dtype=np.float32)
    out1 = model_io._to_numpy(x1)
    assert out1.ndim == 1 and out1.dtype == np.float32 and out1.shape == (3,)

    x2 = np.array([[1.0], [2.0], [3.0]], dtype=np.float32)
    out2 = model_io._to_numpy(x2)
    assert out2.ndim == 1 and out2.dtype == np.float32 and out2.shape == (3,)

    x3 = [1, 2, 3]
    out3 = model_io._to_numpy(x3)
    assert out3.ndim == 1 and out3.dtype == np.float32 and out3.shape == (3,)


# ---------- run_inference / run_embedding / run_inference_with_embedding ----------

class DummyATDict:
    """AudioTagging-like dummy that returns a dict with clipwise, embedding, labels."""
    def __init__(self): self.labels = ["ignored_attr"]
    def inference(self, wav):
        clip = np.array([0.2, 0.8, np.nan], dtype=np.float32)       # include NaN
        emb  = np.array([[1.0, np.inf, -np.inf]], dtype=np.float32)  # 1x3 with infs
        labels = ["dog", "engine", "shotgun"]
        return {"clipwise_output": clip, "embedding": emb, "labels": labels}


class DummyATTuple:
    """AudioTagging-like dummy that returns a tuple (clipwise, embedding, labels)."""
    def inference(self, wav):
        clip = np.array([[0.5], [0.1], [0.3]], dtype=np.float32)  # 3x1 -> flatten
        emb  = np.array([9.0, 8.0, 7.0], dtype=np.float32)
        labels = None  # trigger fallback
        return (clip, emb, labels)


def test_run_inference_with_dict_output():
    """
    run_inference parses dict output and prefers provided labels; clipwise becomes 1-D float32.
    """
    at = DummyATDict()
    clipwise, labels = model_io.run_inference(at, np.zeros(16, dtype=np.float32))
    assert clipwise.shape == (3,) and clipwise.dtype == np.float32
    assert labels == ["dog", "engine", "shotgun"]


def test_run_embedding_with_dict_output():
    """
    run_embedding extracts 'embedding' from dict and flattens to 1-D float32.
    """
    at = DummyATDict()
    emb = model_io.run_embedding(at, np.zeros(16, dtype=np.float32))
    assert emb.shape == (3,) and emb.dtype == np.float32


def test_run_inference_with_tuple_and_label_fallback(monkeypatch):
    """
    When labels are missing, run_inference should fall back to at.labels/package labels/'class_i'.
    Here we force package labels to be None to reach 'class_i'.
    """
    monkeypatch.setattr(model_io, "load_audioset_labels_from_pkg", lambda: None, raising=False)
    at = DummyATTuple()
    clipwise, labels = model_io.run_inference(at, np.zeros(8, dtype=np.float32))
    assert clipwise.shape == (3,)
    assert labels == ["class_0", "class_1", "class_2"]


def test_run_inference_with_embedding_sanitizes_embedding():
    """
    run_inference_with_embedding returns (clipwise, labels, embedding) and sanitizes embedding NaN/Inf -> finite.
    """
    at = DummyATDict()
    clipwise, labels, emb = model_io.run_inference_with_embedding(at, np.zeros(8, dtype=np.float32))
    assert clipwise.shape == (3,)
    assert labels == ["dog", "engine", "shotgun"]
    assert emb.shape == (3,) and emb.dtype == np.float32
    assert np.isfinite(emb).all()


# ---------- segment_waveform ----------

def test_segment_waveform_basic_padding():
    """
    For window>len(wav) and pad_last=True, should return a single padded segment with correct times.
    """
    sr = 32000
    wav = np.zeros(int(0.3 * sr), dtype=np.float32)  # 0.3s
    segs = model_io.segment_waveform(wav, sr=sr, window_sec=0.5, hop_sec=0.25, pad_last=True)
    assert len(segs) == 1
    t0, t1, s = segs[0]
    assert s.shape == (int(0.5 * sr),)
    assert pytest.approx(t0, 1e-6) == 0.0
    assert pytest.approx(t1, 1e-6) == 0.5


def test_segment_waveform_multiple_windows_no_pad():
    """
    For longer wav and pad_last=False, produce multiple windows stepping by hop without tail padding.
    """
    sr = 32000
    wav = np.zeros(int(2.0 * sr), dtype=np.float32)
    segs = model_io.segment_waveform(wav, sr=sr, window_sec=0.5, hop_sec=0.5, pad_last=False)
    assert len(segs) == 4
    for i, (t0, t1, s) in enumerate(segs):
        assert s.shape == (int(0.5 * sr),)
        assert pytest.approx(t0, 1e-6) == i * 0.5
        assert pytest.approx(t1, 1e-6) == i * 0.5 + 0.5


def test_segment_waveform_empty_input():
    """Empty input returns empty segments list."""
    segs = model_io.segment_waveform(np.array([], dtype=np.float32), sr=32000, window_sec=0.5, hop_sec=0.25, pad_last=True)
    assert segs == []


# ---------- aggregate_matrix ----------

def test_aggregate_matrix_mean_and_max():
    """
    Validate mean/max correctness with NaN-aware reductions:
    - mean ignores NaNs (np.nanmean)
    - max ignores NaNs (np.nanmax)
    If a whole column is NaN, result becomes NaN -> then nan_to_num -> 0.0.
    """
    M = np.array([[0.1, 0.9, 0.0],
                  [0.3, np.nan, 0.6],
                  [0.5, 0.4, 0.2]], dtype=np.float32)
    mean_out = model_io.aggregate_matrix(M, mode="mean")
    max_out  = model_io.aggregate_matrix(M, mode="max")

    # mean: second column = mean(0.9, 0.4) = 0.65
    np.testing.assert_allclose(mean_out, np.array([0.3, 0.65, 0.26666668], dtype=np.float32),
                               rtol=1e-6, atol=1e-6)
    # max: second column = max(0.9, 0.4) = 0.9
    np.testing.assert_allclose(max_out,  np.array([0.5, 0.9, 0.6], dtype=np.float32),
                               rtol=1e-6, atol=1e-6)

    assert mean_out.dtype == np.float32 and max_out.dtype == np.float32
    assert mean_out.shape == (3,) and max_out.shape == (3,)


def test_aggregate_matrix_validation_errors():
    """
    Invalid inputs: non-ndarray, wrong ndim, empty windows/classes, unsupported mode -> raise.
    """
    with pytest.raises(TypeError):
        model_io.aggregate_matrix([[0.0, 1.0]], mode="mean")  # not np.ndarray
    with pytest.raises(ValueError):
        model_io.aggregate_matrix(np.zeros((3,), dtype=np.float32), mode="mean")
    with pytest.raises(ValueError):
        model_io.aggregate_matrix(np.zeros((0, 2), dtype=np.float32), mode="mean")
    with pytest.raises(ValueError):
        model_io.aggregate_matrix(np.zeros((2, 0), dtype=np.float32), mode="mean")
    with pytest.raises(ValueError):
        model_io.aggregate_matrix(np.zeros((2, 2), dtype=np.float32), mode="median")  # unsupported
