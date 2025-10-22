import pytest
from pathlib import Path
import sys
from scripts import compare_backbones
import subprocess

def test_compare_backbones_basic(monkeypatch, tmp_path):
    """Test basic functionality of compare_backbones"""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake_audio")
    
    test_args = [
        "compare_backbones.py",
        "--audio", str(audio_file),
        "--device", "cpu",
        "--only", "cnn14", "vggish"  # Only test these two backbones
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    # Mock subprocess.call to avoid actually running classification
    calls = []
    def mock_subprocess_call(cmd):
        calls.append(cmd)
        return 0
    
    monkeypatch.setattr(subprocess, "call", mock_subprocess_call)
    
    # Run main function
    compare_backbones.main()
    
    # Verify correct commands were constructed
    assert len(calls) == 2  # Should have called classify twice (cnn14 and vggish)
    for cmd in calls:
        assert "-m" in cmd
        assert "classification.scripts.classify" in cmd
        assert "--audio" in cmd
        assert "--device" in cmd
        assert "--backbone" in cmd
        assert any(bb in cmd for bb in ["cnn14", "vggish"])

def test_compare_backbones_with_heads(monkeypatch, tmp_path):
    """Test compare_backbones with head models specified"""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake_audio")
    head_file = tmp_path / "head.joblib"
    head_file.write_bytes(b"fake_model")
    
    test_args = [
        "compare_backbones.py",
        "--audio", str(audio_file),
        "--device", "cpu",
        "--head-cnn14", str(head_file),
        "--head-vggish", str(head_file),
        "--only", "cnn14", "vggish"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    calls = []
    def mock_subprocess_call(cmd):
        calls.append(cmd)
        return 0
    
    monkeypatch.setattr(subprocess, "call", mock_subprocess_call)
    
    compare_backbones.main()
    
    # Verify head models were included in commands
    for cmd in calls:
        assert "--head" in cmd
        assert str(head_file) in cmd

def test_compare_backbones_with_db(monkeypatch, tmp_path):
    """Test compare_backbones with database options"""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake_audio")
    
    test_args = [
        "compare_backbones.py",
        "--audio", str(audio_file),
        "--device", "cpu",
        "--write-db",
        "--db-url", "postgresql://fake_url",
        "--db-schema", "test_schema",
        "--only", "cnn14"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    calls = []
    def mock_subprocess_call(cmd):
        calls.append(cmd)
        return 0
    
    monkeypatch.setattr(subprocess, "call", mock_subprocess_call)
    
    compare_backbones.main()
    
    # Verify DB options were included
    cmd = calls[0]
    assert "--write-db" in cmd
    assert "--db-url" in cmd
    assert "postgresql://fake_url" in cmd
    assert "--db-schema" in cmd
    assert "test_schema" in cmd

def test_compare_backbones_error_handling(monkeypatch, tmp_path):
    """Test error handling when classification fails"""
    audio_file = tmp_path / "test.wav"
    audio_file.write_bytes(b"fake_audio")
    
    test_args = [
        "compare_backbones.py",
        "--audio", str(audio_file),
        "--device", "cpu",
        "--only", "cnn14"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    def mock_subprocess_call(cmd):
        return 1  # Simulate failure
    
    monkeypatch.setattr(subprocess, "call", mock_subprocess_call)
    
    # Should not raise exception even if subprocess fails
    compare_backbones.main()