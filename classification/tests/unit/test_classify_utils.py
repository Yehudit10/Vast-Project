import os
import numpy as np
from pathlib import Path
import pytest
import logging
from scripts.classify import env_bool, discover_audio_files, softmax_1d, _setup_logging

def test_env_bool_parsing_cases(monkeypatch):
    """Test env_bool parses truthy and falsy values correctly."""
    monkeypatch.delenv("X", raising=False)
    assert env_bool("X", default=True) is True
    assert env_bool("X", default=False) is False
    for tok in ["1", "true", "TRUE", "yes", "on", " On "]:
        monkeypatch.setenv("E", tok)
        assert env_bool("E", default=False) is True
    for tok in ["0", "false", "FALSE", "no", "off", " ", ""]:
        monkeypatch.setenv("E", tok)
        assert env_bool("E", default=True) is False

def test_env_bool_defaults_and_various_values():
    """Test env_bool default handling and several representations."""
    assert env_bool("NON_EXISTENT_VAR") == False
    assert env_bool("NON_EXISTENT_VAR", default=True) == True
    os.environ["TEST_VAR"] = "1"
    assert env_bool("TEST_VAR") == True
    os.environ["TEST_VAR"] = "false"
    assert env_bool("TEST_VAR") == False

def test_discover_audio_files_accepts_single_supported_file(tmp_path: Path):
    """discover_audio_files accepts a single .wav file path."""
    p = tmp_path / "a.wav"
    p.write_bytes(b"RIFF.WAVE")
    out = discover_audio_files(p)
    assert out == [p]

def test_discover_audio_files_rejects_single_unsupported_file(tmp_path: Path):
    """discover_audio_files returns empty list for unsupported files."""
    p = tmp_path / "a.txt"
    p.write_text("not audio", encoding="utf-8")
    out = discover_audio_files(p)
    assert out == []

def test_discover_audio_files_walks_directory_and_sorts(tmp_path: Path):
    """discover_audio_files finds supported files in directories and sorts them."""
    (tmp_path / "x.wav").write_bytes(b"RIFF")
    (tmp_path / "b.mp3").write_bytes(b"ID3")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.flac").write_bytes(b"fLaC")
    got = discover_audio_files(tmp_path)
    assert [p.name for p in got] == ["b.mp3", "a.flac", "x.wav"]

def test_softmax_1d_edge_cases():
    """softmax_1d handles empty arrays, nan/inf and numerical stability."""
    x = np.array([], dtype=np.float32)
    out = softmax_1d(x)
    assert out.shape == (0,)
    x = np.array([np.nan, np.inf, -np.inf, 0.0], dtype=np.float32)
    out = softmax_1d(x)
    assert np.allclose(out.sum(), 1.0)
    x = np.array([1e9, 1e9 - 1, 1e9 - 2], dtype=np.float32)
    out = softmax_1d(x)
    assert np.isfinite(out).all()
    assert np.argmax(out) == 0

def test_setup_logging_creates_file(tmp_path: Path):
    """_setup_logging configures logging and optionally writes to file."""
    log_file = tmp_path / "test.log"
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    _setup_logging(debug=True, level=None, log_file=None)
    assert logging.getLogger().handlers
    # test file creation
    logging.getLogger().handlers = []
    _setup_logging(debug=False, level="INFO", log_file=str(log_file))
    logging.getLogger().info("test")
    assert log_file.exists()
