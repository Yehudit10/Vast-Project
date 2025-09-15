# tests/unit/test_classify_utils.py
import numpy as np
from pathlib import Path
import pytest

from scripts import classify as CL  # targets scripts/classify.py


def test_env_bool_parsing_cases(monkeypatch):
    # None -> default
    monkeypatch.delenv("X", raising=False)
    assert CL.env_bool("X", default=True) is True
    assert CL.env_bool("X", default=False) is False

    for tok in ["1", "true", "TRUE", "yes", "on", " On "]:
        monkeypatch.setenv("E", tok)
        assert CL.env_bool("E", default=False) is True

    for tok in ["0", "false", "FALSE", "no", "off", " ", ""]:
        monkeypatch.setenv("E", tok)
        assert CL.env_bool("E", default=True) is False


def test_discover_audio_files_accepts_single_supported_file(tmp_path: Path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....WAVE")
    out = CL.discover_audio_files(p)
    assert out == [p]


def test_discover_audio_files_rejects_single_unsupported_file(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("not audio", encoding="utf-8")
    out = CL.discover_audio_files(p)
    assert out == []


def test_discover_audio_files_walks_directory_and_sorts(tmp_path: Path):
    # Mixed valid/invalid and multiple extensions
    (tmp_path / "x.wav").write_bytes(b"RIFF")
    (tmp_path / "b.mp3").write_bytes(b"ID3")
    (tmp_path / "z.txt").write_text("ignore", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.flac").write_bytes(b"fLaC")

    got = CL.discover_audio_files(tmp_path)
    # Implementation sorts by full path -> root files typically come before subdir files
    assert [p.name for p in got] == ["b.mp3", "a.flac", "x.wav"]


# -------- softmax_1d --------

def test_softmax_1d_empty_and_shape():
    x = np.array([], dtype=np.float32)
    out = CL.softmax_1d(x)
    assert out.shape == (0,)

def test_softmax_1d_handles_nan_and_inf():
    x = np.array([np.nan, np.inf, -np.inf, 0.0], dtype=np.float32)
    # nan->0, +/-inf->0 per implementation; result becomes exp([0,0,0,0]) -> uniform
    out = CL.softmax_1d(x)
    assert np.allclose(out.sum(), 1.0)
    assert np.allclose(out, np.full_like(out, 1.0 / out.size))

def test_softmax_1d_numerical_stability_large_values():
    # Very large positives should not overflow due to max-subtraction
    x = np.array([1e9, 1e9 - 1, 1e9 - 2], dtype=np.float32)
    out = CL.softmax_1d(x)
    assert np.isfinite(out).all()
    assert np.argmax(out) == 0
    assert np.isclose(out.sum(), 1.0, rtol=1e-6, atol=1e-6)
