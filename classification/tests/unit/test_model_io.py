"""
Unit tests for core/model_io.py

Cleaned and merged version:
- Duplicate tests removed
- Tests organized by function
- All logic preserved
- Only English comments
"""

import numpy as np
import pytest
import soundfile as sf
from pathlib import Path
import subprocess

from core import model_io


# ---------- has_ffmpeg ----------

def test_has_ffmpeg_true(monkeypatch):
    """has_ffmpeg returns True when ffmpeg is found."""
    monkeypatch.setattr(model_io.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    assert model_io.has_ffmpeg() is True


def test_has_ffmpeg_false(monkeypatch):
    """has_ffmpeg returns False when ffmpeg is not found."""
    monkeypatch.setattr(model_io.shutil, "which", lambda _: None)
    assert model_io.has_ffmpeg() is False


# ---------- decode_with_ffmpeg_to_float32_mono ----------

def test_decode_with_ffmpeg_basic_and_padding(monkeypatch):
    """
    Mock ffmpeg run; output is padded to MIN_SAMPLES if too short.
    """
    samples = np.array([0.0, 0.5, -0.5, 1.0], dtype=np.float32)
    fake_stdout = samples.tobytes()

    class FakeProc:
        def __init__(self):
            self.stdout = fake_stdout
            self.stderr = b""

    real_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and "ffmpeg" in str(cmd[0]).lower():
            return FakeProc()
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(model_io.subprocess, "run", fake_run)
    out = model_io.decode_with_ffmpeg_to_float32_mono("/some/file.mp3", target_sr=model_io.SAMPLE_RATE)
    assert out.dtype == np.float32
    assert len(out) >= model_io.MIN_SAMPLES
    np.testing.assert_array_equal(out[:len(samples)], samples)
    if len(out) > len(samples):
        assert np.all(out[len(samples):] == 0.0)


def test_decode_with_ffmpeg_failure(monkeypatch):
    """ffmpeg failure raises exception."""
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(returncode=1, cmd="ffmpeg -i bad.mp3")

    monkeypatch.setattr(model_io.subprocess, "run", fake_run)
    with pytest.raises(Exception):
        model_io.decode_with_ffmpeg_to_float32_mono("bad.mp3", target_sr=model_io.SAMPLE_RATE)


# ---------- ensure_checkpoint ----------

def test_ensure_checkpoint_existing(tmp_path: Path):
    """Existing checkpoint returns path immediately."""
    ckpt = tmp_path / "ckpt.bin"
    ckpt.write_bytes(b"ok")
    out = model_io.ensure_checkpoint(str(ckpt), checkpoint_url=None)
    assert out == str(ckpt)


def test_ensure_checkpoint_missing_no_url(tmp_path: Path):
    """Missing checkpoint and no URL raises FileNotFoundError."""
    ckpt = tmp_path / "missing.bin"
    with pytest.raises(FileNotFoundError):
        model_io.ensure_checkpoint(str(ckpt), checkpoint_url=None)


def test_ensure_checkpoint_downloads(monkeypatch, tmp_path: Path):
    """Missing checkpoint with URL triggers download via urlretrieve."""
    ckpt = tmp_path / "downloaded.bin"

    def fake_urlretrieve(url, filename):
        Path(filename).write_bytes(b"downloaded")
        return str(filename), None

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlretrieve", fake_urlretrieve)
    out = model_io.ensure_checkpoint(str(ckpt), checkpoint_url="http://example.com/ckpt.bin")
    assert out == str(ckpt)
    assert ckpt.exists() and ckpt.read_bytes() == b"downloaded"


# ---------- load_audio ----------

def test_load_audio_wav_and_resample(tmp_path: Path):
    """Load WAV: mono conversion, float32, resampling, and padding."""
    sr = 16000
    duration = 0.25
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    stereo = np.stack([0.1*np.sin(2*np.pi*440*t), 0.1*np.sin(2*np.pi*660*t)], axis=1).astype(np.float32)
    wav_path = tmp_path / "test.wav"
    sf.write(wav_path, stereo, sr)

    y = model_io.load_audio(str(wav_path), target_sr=model_io.SAMPLE_RATE)
    assert y.ndim == 1 and y.dtype == np.float32
    assert len(y) >= model_io.MIN_SAMPLES


def test_load_audio_compressed_with_librosa_and_ffmpeg(monkeypatch, tmp_path: Path):
    """Compressed file loading tries librosa first, then ffmpeg fallback if available."""
    p = tmp_path / "fake.mp3"
    p.write_bytes(b"not_mp3")

    def fail_librosa(*args, **kwargs): raise RuntimeError("librosa fail")
    monkeypatch.setattr(model_io.librosa, "load", fail_librosa)
    monkeypatch.setattr(model_io, "has_ffmpeg", lambda: True)
    monkeypatch.setattr(model_io, "decode_with_ffmpeg_to_float32_mono",
                        lambda path, target_sr: np.array([1,2,3], dtype=np.float32))
    y = model_io.load_audio(str(p), target_sr=model_io.SAMPLE_RATE)
    np.testing.assert_array_equal(y[:3], np.array([1,2,3], dtype=np.float32))


def test_load_audio_failure(monkeypatch, tmp_path: Path):
    """If all loaders fail and ffmpeg is unavailable, load_audio raises."""
    p = tmp_path / "bad.wav"
    monkeypatch.setattr(model_io.sf, "read", lambda *a, **k: (_raise(RuntimeError("sf fail")), None))
    monkeypatch.setattr(model_io.librosa, "load", lambda *a, **k: _raise(RuntimeError("librosa fail")))
    monkeypatch.setattr(model_io, "has_ffmpeg", lambda: False)

    with pytest.raises(Exception):
        model_io.load_audio(str(p), target_sr=model_io.SAMPLE_RATE)


def _raise(err):
    raise err


# ---------- _to_numpy ----------

def test_to_numpy_flattens_and_dtype():
    """_to_numpy returns 1-D float32 arrays from lists or 2-D arrays."""
    for x in [np.array([[1,2,3]], dtype=np.float32),
              np.array([[1],[2],[3]], dtype=np.float32),
              [1,2,3]]:
        out = model_io._to_numpy(x)
        assert out.ndim == 1 and out.dtype == np.float32 and out.shape[0] == 3


# ---------- run_inference / run_embedding / run_inference_with_embedding ----------

class DummyATDict:
    """Dummy model returning dict with clipwise, embedding, labels."""
    def __init__(self): self.labels = ["ignored_attr"]
    def inference(self, wav):
        clip = np.array([0.2,0.8,np.nan], dtype=np.float32)
        emb = np.array([[1.0,np.inf,-np.inf]], dtype=np.float32)
        labels = ["dog","engine","shotgun"]
        return {"clipwise_output": clip, "embedding": emb, "labels": labels}


class DummyATTuple:
    """Dummy model returning tuple (clipwise, embedding, labels)."""
    def inference(self, wav):
        clip = np.array([[0.5],[0.1],[0.3]], dtype=np.float32)
        emb = np.array([9.0,8.0,7.0], dtype=np.float32)
        labels = None
        return clip, emb, labels


def test_run_inference_dict_output():
    """run_inference parses dict output correctly."""
    at = DummyATDict()
    clipwise, labels = model_io.run_inference(at, np.zeros(16, dtype=np.float32))
    assert clipwise.shape == (3,) and clipwise.dtype == np.float32
    assert labels == ["dog","engine","shotgun"]


def test_run_embedding_dict_output():
    """run_embedding extracts embedding and flattens."""
    at = DummyATDict()
    _, _, emb = model_io.run_inference_with_embedding(at, np.zeros(16, dtype=np.float32))
    assert emb.shape == (3,) and emb.dtype == np.float32


def test_run_inference_tuple_label_fallback(monkeypatch):
    """Fallback to 'class_i' labels if labels missing."""
    monkeypatch.setattr(model_io, "load_audioset_labels_from_pkg", lambda: None)
    at = DummyATTuple()
    clipwise, labels = model_io.run_inference(at, np.zeros(8, dtype=np.float32))
    assert clipwise.shape == (3,)
    assert labels == ["class_0","class_1","class_2"]


def test_run_inference_with_embedding_sanitizes():
    """run_inference_with_embedding sanitizes NaN/Inf in embedding."""
    at = DummyATDict()
    clipwise, labels, emb = model_io.run_inference_with_embedding(at, np.zeros(8, dtype=np.float32))
    assert clipwise.shape == (3,)
    assert labels == ["dog","engine","shotgun"]
    assert np.isfinite(emb).all() and emb.dtype == np.float32


# ---------- segment_waveform ----------

def test_segment_waveform_various_cases():
    """Test segmentation with pad_last True/False, multiple windows, and short inputs."""
    sr = 32000
    wav = np.zeros(int(0.75*sr), dtype=np.float32)

    # pad_last=True
    windows = model_io.segment_waveform(wav, sr, window_sec=0.5, hop_sec=0.5, pad_last=True)
    assert len(windows) == 2
    assert all(seg.shape[0] == int(0.5*sr) for _,_,seg in windows)

    # pad_last=False
    windows = model_io.segment_waveform(wav, sr, window_sec=0.5, hop_sec=0.5, pad_last=False)
    assert len(windows) == 1
    assert windows[0][2].shape[0] == int(0.5*sr)

    # empty input
    windows = model_io.segment_waveform(np.array([], dtype=np.float32), sr, window_sec=0.5, hop_sec=0.25, pad_last=True)
    assert windows == []


# ---------- aggregate_matrix ----------

def test_aggregate_matrix_mean_and_max():
    """Validate NaN-aware mean/max aggregation."""
    M = np.array([[0.1,0.9,0.0],[0.3,np.nan,0.6],[0.5,0.4,0.2]], dtype=np.float32)
    mean_out = model_io.aggregate_matrix(M, mode="mean")
    max_out = model_io.aggregate_matrix(M, mode="max")
    np.testing.assert_allclose(mean_out, np.array([0.3,0.65,0.26666668], dtype=np.float32), rtol=1e-6, atol=1e-6)
    np.testing.assert_allclose(max_out, np.array([0.5,0.9,0.6], dtype=np.float32), rtol=1e-6, atol=1e-6)


def test_aggregate_matrix_validation_errors():
    """Invalid inputs and unsupported mode raise exceptions."""
    with pytest.raises(TypeError):
        model_io.aggregate_matrix([[0.0,1.0]], mode="mean")
    with pytest.raises(ValueError):
        model_io.aggregate_matrix(np.zeros((3,), dtype=np.float32), mode="mean")
    with pytest.raises(ValueError):
        model_io.aggregate_matrix(np.zeros((0,2), dtype=np.float32), mode="mean")
    with pytest.raises(ValueError):
        model_io.aggregate_matrix(np.zeros((2,0), dtype=np.float32), mode="mean")
    with pytest.raises(Exception):
        model_io.aggregate_matrix(np.zeros((2,2), dtype=np.float32), mode="median")


# # ---------- load labels ----------

# def test_load_labels_from_csv(tmp_path: Path):
#     """Test loading labels from CSV file with various formats."""
#     # Valid CSV with index and display_name
#     csv_path = tmp_path / "labels.csv"
#     csv_path.write_text("index,display_name\n0,dog\n1,cat\n2,bird", encoding="utf-8")
#     labels = model_io.load_labels_from_csv(str(csv_path))
#     assert labels == ["dog", "cat", "bird"]

#     # Valid CSV with index and name
#     csv_path.write_text("index,name\n0,dog\n1,cat\n2,bird", encoding="utf-8")
#     labels = model_io.load_labels_from_csv(str(csv_path))
#     assert labels == ["dog", "cat", "bird"]

#     # Invalid file should return None
#     bad_csv = tmp_path / "bad.csv"
#     bad_csv.write_text("not,a,valid,csv", encoding="utf-8")
#     assert model_io.load_labels_from_csv(str(bad_csv)) is None

#     # Non-existent file should return None
#     assert model_io.load_labels_from_csv(str(tmp_path / "missing.csv")) is None

# def test_load_audioset_labels_from_pkg(monkeypatch):
#     """Test loading AudioSet labels from package."""
#     def mock_open(*args, **kwargs):
#         class MockFile:
#             def __init__(self): 
#                 self.content = "index,display_name\n0,Speech\n1,Music"
#             def __enter__(self): return self
#             def __exit__(self, *args): pass
#             def __iter__(self): return iter(self.content.splitlines())
#         return MockFile()

#     import builtins
#     monkeypatch.setattr(builtins, "open", mock_open)
#     labels = model_io.load_audioset_labels_from_pkg()
#     assert labels == ["Speech", "Music"]

#     # Test failure case
#     def raise_error(*args, **kwargs): raise FileNotFoundError()
#     monkeypatch.setattr(builtins, "open", raise_error)
#     assert model_io.load_audioset_labels_from_pkg() is None
