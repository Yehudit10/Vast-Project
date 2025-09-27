# tests/unit/test_classify_utils.py
import os
import numpy as np
from pathlib import Path
import pytest
import logging

from scripts.classify import env_bool, discover_audio_files, softmax_1d, _setup_logging


def test_env_bool_parsing_cases(monkeypatch):
    # None -> default
    monkeypatch.delenv("X", raising=False)
    assert env_bool("X", default=True) is True
    assert env_bool("X", default=False) is False

    for tok in ["1", "true", "TRUE", "yes", "on", " On "]:
        monkeypatch.setenv("E", tok)
        assert env_bool("E", default=False) is True

    for tok in ["0", "false", "FALSE", "no", "off", " ", ""]:
        monkeypatch.setenv("E", tok)
        assert env_bool("E", default=True) is False


def test_env_bool():
    # Test default values
    assert env_bool("NON_EXISTENT_VAR") == False
    assert env_bool("NON_EXISTENT_VAR", default=True) == True
    
    # Test various truthy values
    os.environ["TEST_VAR"] = "1"
    assert env_bool("TEST_VAR") == True
    os.environ["TEST_VAR"] = "true"
    assert env_bool("TEST_VAR") == True
    os.environ["TEST_VAR"] = "YES"
    assert env_bool("TEST_VAR") == True
    os.environ["TEST_VAR"] = "on"
    assert env_bool("TEST_VAR") == True
    
    # Test various falsy values
    os.environ["TEST_VAR"] = "0"
    assert env_bool("TEST_VAR") == False
    os.environ["TEST_VAR"] = "false"
    assert env_bool("TEST_VAR") == False
    os.environ["TEST_VAR"] = "no"
    assert env_bool("TEST_VAR") == False
    os.environ["TEST_VAR"] = "off"
    assert env_bool("TEST_VAR") == False


def test_discover_audio_files_accepts_single_supported_file(tmp_path: Path):
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF....WAVE")
    out = discover_audio_files(p)
    assert out == [p]


def test_discover_audio_files_rejects_single_unsupported_file(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("not audio", encoding="utf-8")
    out = discover_audio_files(p)
    assert out == []


def test_discover_audio_files_walks_directory_and_sorts(tmp_path: Path):
    # Mixed valid/invalid and multiple extensions
    (tmp_path / "x.wav").write_bytes(b"RIFF")
    (tmp_path / "b.mp3").write_bytes(b"ID3")
    (tmp_path / "z.txt").write_text("ignore", encoding="utf-8")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.flac").write_bytes(b"fLaC")

    got = discover_audio_files(tmp_path)
    # Implementation sorts by full path -> root files typically come before subdir files
    assert [p.name for p in got] == ["b.mp3", "a.flac", "x.wav"]


def test_discover_audio_files(tmp_path: Path):
    # Create test audio files with supported extensions
    (tmp_path / "test1.wav").touch()
    (tmp_path / "test2.WAV").touch()
    (tmp_path / "test3.mp3").touch()
    (tmp_path / "test4.txt").touch()
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "test5.wav").touch()
    
    # Test single file input
    assert len(discover_audio_files(tmp_path / "test1.wav")) == 1
    assert len(discover_audio_files(tmp_path / "test4.txt")) == 0
    
    # Test directory input
    files = discover_audio_files(tmp_path)
    assert all(f.suffix.lower() in [".wav", ".mp3"] for f in files)
    assert any(f.name == "test5.wav" for f in files)  # Should find files in subdirs


# -------- softmax_1d --------

def test_softmax_1d_empty_and_shape():
    x = np.array([], dtype=np.float32)
    out = softmax_1d(x)
    assert out.shape == (0,)


def test_softmax_1d_handles_nan_and_inf():
    x = np.array([np.nan, np.inf, -np.inf, 0.0], dtype=np.float32)
    # nan->0, +/-inf->0 per implementation; result becomes exp([0,0,0,0]) -> uniform
    out = softmax_1d(x)
    assert np.allclose(out.sum(), 1.0)
    assert np.allclose(out, np.full_like(out, 1.0 / out.size))


def test_softmax_1d_numerical_stability_large_values():
    # Very large positives should not overflow due to max-subtraction
    x = np.array([1e9, 1e9 - 1, 1e9 - 2], dtype=np.float32)
    out = softmax_1d(x)
    assert np.isfinite(out).all()
    assert np.argmax(out) == 0
    assert np.isclose(out.sum(), 1.0, rtol=1e-6, atol=1e-6)


def test_softmax_1d():
    # Test empty array
    x = np.array([], dtype=np.float32)
    assert len(softmax_1d(x)) == 0
    
    # Test normal case
    x = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    result = softmax_1d(x)
    assert result.dtype == np.float32
    assert np.allclose(np.sum(result), 1.0)
    assert result[2] > result[1] > result[0]  # Should maintain ordering
    
    # Test with NaN and inf values
    x = np.array([np.nan, np.inf, -np.inf, 1.0], dtype=np.float32)
    result = softmax_1d(x)
    assert np.all(np.isfinite(result))
    assert np.allclose(np.sum(result), 1.0)
    
    # Test with all zeros
    x = np.zeros(5, dtype=np.float32)
    result = softmax_1d(x)
    assert np.allclose(result, 0.2)  # Should be uniform distribution


def test_setup_logging(tmp_path: Path):
    log_file = tmp_path / "test.log"
    
    # Cleanup any existing handlers before test
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    
    # Test with debug=True
    _setup_logging(debug=True, level=None, log_file=None)
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
    
    # Cleanup again
    for h in list(root.handlers):
        root.removeHandler(h)
    
    # Test with custom level
    _setup_logging(debug=False, level="ERROR", log_file=None)
    assert logging.getLogger().getEffectiveLevel() == logging.ERROR
    
    # Cleanup again
    for h in list(root.handlers):
        root.removeHandler(h)
    
    # Test with invalid level, should fallback to INFO
    _setup_logging(debug=False, level="INVALID", log_file=None)
    lvl = logging.getLogger().getEffectiveLevel()
    assert lvl in (logging.INFO, logging.WARNING)
    
    # Cleanup again
    for h in list(root.handlers):
        root.removeHandler(h)
    
    # Test with log file
    _setup_logging(debug=False, level=None, log_file=str(log_file))
    assert any(isinstance(h, logging.FileHandler) for h in logging.getLogger().handlers)
