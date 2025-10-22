import pytest
from pathlib import Path
import numpy as np
from pipeline import train_head
import json

def test_embed_clip_vggish(monkeypatch):
    """Test _embed_clip function with vggish backbone"""
    wav = np.zeros(16000, dtype=np.float32)  # 1 second of silence
    
    def mock_vggish(*args, **kwargs):
        return [np.ones((128,), dtype=np.float32)]
    
    monkeypatch.setattr(train_head, "run_vggish_embeddings", mock_vggish)
    result = train_head._embed_clip("vggish", None, wav, "cpu", None)
    assert result.shape == (128,)
    assert result.dtype == np.float32

def test_embed_clip_ast(monkeypatch):
    """Test _embed_clip function with AST backbone"""
    wav = np.zeros(16000, dtype=np.float32)
    
    def mock_ast(*args, **kwargs):
        return np.ones((768,), dtype=np.float32)
    
    monkeypatch.setattr(train_head, "run_ast_embedding", mock_ast)
    result = train_head._embed_clip("ast", None, wav, "cpu", "mock_dir")
    assert result.shape == (768,)
    
    # Test AST without model directory
    with pytest.raises(RuntimeError):
        train_head._embed_clip("ast", None, wav, "cpu", None)

def test_embed_clip_fusion(monkeypatch):
    """Test _embed_clip function with fusion backbone"""
    wav = np.zeros(16000, dtype=np.float32)
    
    def mock_cnn14(*args, **kwargs):
        return np.ones((2048,), dtype=np.float32)
    
    def mock_vggish(*args, **kwargs):
        return [np.ones((128,), dtype=np.float32)]
    
    monkeypatch.setattr(train_head, "run_cnn14_embedding", mock_cnn14)
    monkeypatch.setattr(train_head, "run_vggish_embeddings", mock_vggish)
    
    result = train_head._embed_clip("fusion", "mock_model", wav, "cpu", None)
    assert result.shape == (2176,)  # 2048 + 128
    assert result.dtype == np.float32

def test_main_with_ast(monkeypatch, tmp_path: Path):
    """Test main function with AST backbone"""
    # Create test data structure
    train_dir = tmp_path / "train"
    train_dir.mkdir()
    classes = ["birds", "vehicle"]
    for cls in classes:
        class_dir = train_dir / cls
        class_dir.mkdir()
        (class_dir / "test.wav").write_bytes(b"fake_audio")
    
    # Mock command line arguments
    test_args = [
        "train_head.py",
        "--train-dir", str(train_dir),
        "--backbone", "ast",
        "--ast-model-dir", str(tmp_path / "ast_model"),
        "--device", "cpu",
        "--out", str(tmp_path / "head.joblib"),
        "--classes", ",".join(classes)
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    # Mock dependencies
    def mock_ast(*args, **kwargs):
        return np.ones((768,), dtype=np.float32)
    
    def mock_load_audio(*args, **kwargs):
        return np.zeros(16000, dtype=np.float32)
    
    monkeypatch.setattr(train_head, "run_ast_embedding", mock_ast)
    monkeypatch.setattr(train_head, "load_audio", mock_load_audio)
    monkeypatch.setattr(train_head.joblib, "dump", lambda obj, path: Path(path).write_bytes(b"model"))
    
    # Run main
    train_head.main()
    
    # Verify outputs
    assert (tmp_path / "head.joblib").exists()
    assert (tmp_path / "head.joblib.meta.json").exists()
    
    # Verify meta file content
    meta = json.loads((tmp_path / "head.joblib.meta.json").read_text())
    assert meta["backbone"] == "ast"
    assert meta["class_order"] == classes
    assert meta["embedding_dim"] == 768

def test_main_invalid_inputs(monkeypatch, tmp_path: Path):
    """Test main function with invalid inputs"""
    # Test missing train directory
    test_args = [
        "train_head.py",
        "--backbone", "cnn14",
        "--device", "cpu"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    with pytest.raises(SystemExit):
        train_head.main()
    
    # Test invalid test size
    test_args = [
        "train_head.py",
        "--train-dir", str(tmp_path),
        "--backbone", "cnn14",
        "--device", "cpu",
        "--test-size", "0.95"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    with pytest.raises(SystemExit):
        train_head.main()
    
    # Test AST without model directory
    test_args = [
        "train_head.py",
        "--train-dir", str(tmp_path),
        "--backbone", "ast",
        "--device", "cpu"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    with pytest.raises(SystemExit):
        train_head.main()