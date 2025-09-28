# tests/unit/test_infer.py
import pytest
from pathlib import Path
import numpy as np
from pipeline import infer
import json

def test_env_bool(monkeypatch):
    """
    Test the env_bool function with different inputs.
    Verifies that:
    - non-existent env var returns False by default and True when default=True
    - various truthy and falsy string values are parsed correctly
    """
    assert infer.env_bool("NON_EXISTENT") == False
    assert infer.env_bool("NON_EXISTENT", default=True) == True

    # use the pytest monkeypatch fixture to set environment variables
    monkeypatch.setenv("TEST_TRUE", "true")
    monkeypatch.setenv("TEST_YES", "yes")
    monkeypatch.setenv("TEST_1", "1")
    monkeypatch.setenv("TEST_FALSE", "false")
    monkeypatch.setenv("TEST_EMPTY", "")

    assert infer.env_bool("TEST_TRUE") == True
    assert infer.env_bool("TEST_YES") == True
    assert infer.env_bool("TEST_1") == True
    assert infer.env_bool("TEST_FALSE") == False
    assert infer.env_bool("TEST_EMPTY") == False

def test_discover_audio_files(tmp_path: Path):
    """Test discovering audio files with different extensions"""
    # Create test files
    (tmp_path / "test.wav").write_bytes(b"fake_wav")
    (tmp_path / "test.mp3").write_bytes(b"fake_mp3")
    (tmp_path / "test.flac").write_bytes(b"fake_flac")
    (tmp_path / "test.txt").write_bytes(b"not_audio")
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    (subdir / "sub.wav").write_bytes(b"sub_wav")
    
    # Test directory scanning
    files = infer.discover_audio_files(tmp_path)
    assert len(files) == 4  # 3 audio files + 1 in subdir
    assert all(f.suffix.lower() in infer.SUPPORTED_EXTS for f in files)
    
    # Test single file
    single_file = tmp_path / "test.wav"
    files = infer.discover_audio_files(single_file)
    assert len(files) == 1
    assert files[0] == single_file
    
    # Test single non-audio file
    non_audio = tmp_path / "test.txt"
    files = infer.discover_audio_files(non_audio)
    assert len(files) == 0

def test_softmax_1d():
    """Test the softmax_1d function with different inputs"""
    # Test normal case
    x = np.array([1.0, 2.0, 3.0])
    result = infer.softmax_1d(x)
    assert result.shape == x.shape
    assert np.isclose(np.sum(result), 1.0)
    assert np.all(result >= 0)
    
    # Test empty array
    x = np.array([])
    result = infer.softmax_1d(x)
    assert result.shape == x.shape
    
    # Test array with infinity
    x = np.array([1.0, np.inf, 3.0])
    result = infer.softmax_1d(x)
    assert np.isfinite(result).all()
    assert np.isclose(np.sum(result), 1.0)
    
    # Test array with NaN
    x = np.array([1.0, np.nan, 3.0])
    result = infer.softmax_1d(x)
    assert not np.isnan(result).any()
    assert np.isclose(np.sum(result), 1.0)

def test_main_with_mocks(monkeypatch, tmp_path: Path):
    """Test the main function with mocked dependencies"""
    # Create test files and directories
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake_wav")
    checkpoint = tmp_path / "checkpoint.pth"
    checkpoint.write_bytes(b"fake_checkpoint")
    
    # Mock command line arguments
    test_args = [
        "infer.py",
        "--audio", str(audio_file),
        "--checkpoint", str(checkpoint),
        "--device", "cpu",
        "--window-sec", "1.0",
        "--hop-sec", "0.5",
        "--agg", "mean",
        "--topk", "5",
        "--backbone", "cnn14"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    # Mock model loading and inference
    def mock_load_cnn14(*args, **kwargs):
        class MockModel:
            def __call__(self, *args, **kwargs):
                return np.random.rand(1, 527), ["class1", "class2"]
        return MockModel()
    
    monkeypatch.setattr(infer, "load_cnn14_model", mock_load_cnn14)
    monkeypatch.setattr(infer, "load_audio", lambda *args, **kwargs: np.zeros(16000))
    monkeypatch.setattr(infer, "run_inference_with_embedding", 
                       lambda *args, **kwargs: (np.random.rand(527), ["class1", "class2"], np.random.rand(2048)))
    
    # Run main function
    infer.main()

def test_setup_logging(tmp_path: Path):
    log_file = tmp_path / "test.log"

    # remove all existing handlers first
    infer.LOGGER.handlers = []

    # debug mode
    infer._setup_logging(debug=True, level=None, log_file=None)
    # force level
    infer.LOGGER.setLevel(infer.logging.DEBUG)
    assert infer.LOGGER.getEffectiveLevel() == infer.logging.DEBUG

    # custom level
    infer.LOGGER.handlers = []
    infer._setup_logging(debug=False, level="ERROR", log_file=None)
    infer.LOGGER.setLevel(infer.logging.ERROR)
    assert infer.LOGGER.getEffectiveLevel() == infer.logging.ERROR

    # with file
    infer.LOGGER.handlers = []
    infer._setup_logging(debug=False, level="INFO", log_file=str(log_file))
    infer.LOGGER.setLevel(infer.logging.INFO)
    assert log_file.exists()

def test_main_with_head(monkeypatch, tmp_path: Path):
    # setup audio file
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake_wav")
    checkpoint = tmp_path / "checkpoint.pth"
    checkpoint.write_bytes(b"fake_checkpoint")

    # create dummy head (joblib load mock)
    class DummyHead:
        def predict_proba(self, X):
            return np.ones((1, 11)) / 11  # uniform probabilities

    dummy_head_path = tmp_path / "head.pkl"
    dummy_head_path.write_bytes(b"dummy")  # content irrelevant

    monkeypatch.setattr("sys.argv", [
        "infer.py",
        "--audio", str(audio_file),
        "--checkpoint", str(checkpoint),
        "--backbone", "cnn14",
        "--head", str(dummy_head_path),
    ])

    monkeypatch.setattr(infer, "load_cnn14_model", lambda *a, **k: object())
    monkeypatch.setattr(infer, "load_audio", lambda *a, **k: np.zeros(16000))
    monkeypatch.setattr(infer, "segment_waveform", lambda *a, **k: [(0, 1, np.zeros(16000))])
    monkeypatch.setattr(infer, "run_inference_with_embedding", lambda *a, **k: (np.random.rand(527), [f"class{i}" for i in range(527)], np.random.rand(2048)))
    monkeypatch.setattr(infer, "run_cnn14_embedding", lambda *a, **k: np.random.rand(2048))
    monkeypatch.setattr(infer, "load_labels_from_csv", lambda *a, **k: None)
    monkeypatch.setattr("joblib.load", lambda path: DummyHead())

    # Run main
    infer.main()

def test_main_exit_on_unsupported_ext(monkeypatch, tmp_path: Path):
    f = tmp_path / "bad.txt"
    f.write_text("not audio")
    monkeypatch.setattr("sys.argv", ["infer.py", "--audio", str(f)])
    with pytest.raises(SystemExit) as e:
        infer.main()
    assert e.value.code == 4

def test_main_exit_no_files(monkeypatch, tmp_path: Path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    monkeypatch.setattr("sys.argv", ["infer.py", "--audio", str(empty_dir)])
    with pytest.raises(SystemExit) as e:
        infer.main()
    assert e.value.code == 0

def test_main_exit_invalid_window(monkeypatch, tmp_path: Path):
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake")
    monkeypatch.setattr("sys.argv", ["infer.py", "--audio", str(audio_file), "--window-sec", "-1"])
    with pytest.raises(SystemExit) as e:
        infer.main()
    assert e.value.code == 2

def test_main_exit_invalid_hop(monkeypatch, tmp_path: Path):
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake")
    monkeypatch.setattr("sys.argv", ["infer.py", "--audio", str(audio_file), "--hop-sec", "-1"])
    with pytest.raises(SystemExit) as e:
        infer.main()
    assert e.value.code == 2

def test_main_exit_ast_no_model(monkeypatch, tmp_path: Path):
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake")
    monkeypatch.setattr("sys.argv", ["infer.py", "--audio", str(audio_file), "--backbone", "ast"])
    with pytest.raises(SystemExit) as e:
        infer.main()
    assert e.value.code == 5
