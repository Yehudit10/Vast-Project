import pytest
from pathlib import Path
import numpy as np
from scripts import train_head
from unittest.mock import patch, MagicMock
import tempfile
import os

def test_embed_clip_vggish(monkeypatch):
    """Test _embed_clip with VGGish backbone"""
    # Mock VGGish embeddings
    mock_emb = np.ones((1, 128), dtype=np.float32)
    def mock_vggish(*args, **kwargs):
        return mock_emb
    
    monkeypatch.setattr("scripts.train_head.run_vggish_embeddings", mock_vggish)
    
    wav = np.random.randn(16000).astype(np.float32)
    result = train_head._embed_clip("vggish", None, wav, "cpu", None)
    
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    assert result.shape == (128,)

def test_embed_clip_ast(monkeypatch):
    """Test _embed_clip with AST backbone"""
    # Mock AST embeddings
    mock_emb = np.ones(768, dtype=np.float32)
    def mock_ast(*args, **kwargs):
        return mock_emb
    
    monkeypatch.setattr("scripts.train_head.run_ast_embedding", mock_ast)
    
    wav = np.random.randn(16000).astype(np.float32)
    result = train_head._embed_clip("ast", None, wav, "cpu", "/fake/ast/dir")
    
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    assert result.shape == (768,)
    
    # Test error when ast_model_dir is missing
    with pytest.raises(RuntimeError):
        train_head._embed_clip("ast", None, wav, "cpu", None)

def test_embed_clip_fusion(monkeypatch):
    """Test _embed_clip with fusion backbone"""
    # Mock both CNN14 and VGGish embeddings
    mock_cnn14 = np.ones(2048, dtype=np.float32)
    mock_vggish = np.ones((1, 128), dtype=np.float32)
    
    def mock_cnn14_emb(*args, **kwargs):
        return mock_cnn14
        
    def mock_vggish_emb(*args, **kwargs):
        return mock_vggish
    
    monkeypatch.setattr("scripts.train_head.run_cnn14_embedding", mock_cnn14_emb)
    monkeypatch.setattr("scripts.train_head.run_vggish_embeddings", mock_vggish_emb)
    
    wav = np.random.randn(16000).astype(np.float32)
    mock_at = MagicMock()
    result = train_head._embed_clip("fusion", mock_at, wav, "cpu", None)
    
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    assert result.shape == (2176,)  # 2048 + 128
    
    # Test error when at is None
    with pytest.raises(AssertionError):
        train_head._embed_clip("fusion", None, wav, "cpu", None)

def test_discover_labeled_files(tmp_path):
    """Test discover_labeled_files with different scenarios"""
    # Create test directory structure
    (tmp_path / "birds").mkdir()
    (tmp_path / "vehicle").mkdir()
    (tmp_path / "other").mkdir()
    
    # Create some test files
    (tmp_path / "birds" / "test1.wav").write_bytes(b"test")
    (tmp_path / "birds" / "test2.mp3").write_bytes(b"test")
    (tmp_path / "vehicle" / "test3.wav").write_bytes(b"test")
    (tmp_path / "other" / "not_audio.txt").write_bytes(b"test")
    
    class_order = ["birds", "vehicle", "other"]
    files = train_head.discover_labeled_files(tmp_path, class_order)
    
    # Should find 3 audio files (2 in birds, 1 in vehicle)
    assert len(files) == 3
    
    # Check that all found files are audio files
    for path, label in files:
        assert path.suffix.lower() in train_head.SUPPORTED_EXTS
        assert label in class_order
        
    # Test with missing directory
    class_order_with_missing = ["birds", "vehicle", "missing"]
    files = train_head.discover_labeled_files(tmp_path, class_order_with_missing)
    assert len(files) == 3  # Should still find the same files

def test_main_with_mocks(monkeypatch, tmp_path):
    """Test main function with mocked dependencies"""
    # Create test files and structure
    train_dir = tmp_path / "train"
    (train_dir / "birds").mkdir(parents=True)
    (train_dir / "birds" / "test1.wav").write_bytes(b"test")
    (train_dir / "birds" / "test2.wav").write_bytes(b"test")

    (train_dir / "vehicle").mkdir()
    (train_dir / "vehicle" / "test3.wav").write_bytes(b"test")
    
    head_out = tmp_path / "head.joblib"
    
    # Mock command line arguments
    test_args = [
        "train_head.py",
        "--train-dir", str(train_dir),
        "--device", "cpu",
        "--out", str(head_out),
        "--classes", "birds, vehicle",
        "--backbone", "vggish"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    # Mock audio loading and embeddings
    def mock_load_audio(*args, **kwargs):
        return np.zeros(16000, dtype=np.float32)
        
    def mock_vggish_embeddings(*args, **kwargs):
        return np.zeros((1, 128), dtype=np.float32)
    
    monkeypatch.setattr("scripts.train_head.load_audio", mock_load_audio)
    monkeypatch.setattr("scripts.train_head.run_vggish_embeddings", mock_vggish_embeddings)
    
    # Run main function
    train_head.main()
    
    # Verify outputs
    assert head_out.exists()
    assert (head_out.parent / (head_out.name + ".meta.json")).exists()

def test_main_error_cases(monkeypatch, tmp_path):
    """Test main function error handling"""
    # Test missing train_dir
    test_args = ["train_head.py"]
    monkeypatch.setattr("sys.argv", test_args)
    
    with pytest.raises(SystemExit):
        train_head.main()
    
    # Test empty class list
    test_args = [
        "train_head.py",
        "--train-dir", str(tmp_path),
        "--classes", ""
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    with pytest.raises(SystemExit):
        train_head.main()
    
    # Test AST without model dir
    test_args = [
        "train_head.py",
        "--train-dir", str(tmp_path),
        "--backbone", "ast"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    with pytest.raises(SystemExit):
        train_head.main()