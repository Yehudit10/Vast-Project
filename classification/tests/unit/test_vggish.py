import pytest
import numpy as np
import torch
from backbones import vggish
from unittest.mock import patch, MagicMock

def test_vggish_embed_window_basic(monkeypatch):
    """Test basic functionality of _vggish_embed_window"""
    # Mock torchvggish components
    mock_examples = np.zeros((2, 1, 96, 64), dtype=np.float32)
    mock_feats = torch.zeros((2, 128), dtype=torch.float32)
    
    class MockVGGish:
        def to(self, device):
            return self
            
        def eval(self):
            return self
            
        def __call__(self, x):
            return mock_feats
    
    def mock_waveform_to_examples(*args, **kwargs):
        return mock_examples
        
    monkeypatch.setattr(vggish, "_HAS_VGGISH", True)
    monkeypatch.setattr(vggish.vggish_input, "waveform_to_examples", mock_waveform_to_examples)
    monkeypatch.setattr(vggish, "vggish", lambda: MockVGGish())
    
    wav = np.random.randn(16000).astype(np.float32)
    result = vggish._vggish_embed_window(wav, sr=16000, device="cpu")
    
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    assert result.shape == (128,)

def test_vggish_embed_window_empty_input(monkeypatch):
    """Test _vggish_embed_window with empty input"""
    # Mock components to return empty examples
    def mock_waveform_to_examples(*args, **kwargs):
        return np.array([], dtype=np.float32)
    
    monkeypatch.setattr(vggish, "_HAS_VGGISH", True)
    monkeypatch.setattr(vggish.vggish_input, "waveform_to_examples", mock_waveform_to_examples)
    
    wav = np.array([], dtype=np.float32)
    result = vggish._vggish_embed_window(wav, sr=16000, device="cpu")
    
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32
    assert result.shape == (128,)
    assert np.all(result == 0)

def test_vggish_embed_window_3d_input(monkeypatch):
    """Test _vggish_embed_window with 3D input from waveform_to_examples"""
    mock_examples = np.zeros((2, 96, 64), dtype=np.float32)
    mock_feats = torch.zeros((2, 128), dtype=torch.float32)
    
    class MockVGGish:
        def to(self, device):
            return self
            
        def eval(self):
            return self
            
        def __call__(self, x):
            return mock_feats
    
    def mock_waveform_to_examples(*args, **kwargs):
        return mock_examples
    
    monkeypatch.setattr(vggish, "_HAS_VGGISH", True)
    monkeypatch.setattr(vggish.vggish_input, "waveform_to_examples", mock_waveform_to_examples)
    monkeypatch.setattr(vggish, "vggish", lambda: MockVGGish())
    
    wav = np.random.randn(16000).astype(np.float32)
    result = vggish._vggish_embed_window(wav, sr=16000, device="cpu")
    
    assert isinstance(result, np.ndarray)
    assert result.shape == (128,)

def test_run_embedding_vggish_short_input(monkeypatch):
    """Test run_embedding_vggish with input shorter than window"""
    def mock_embed_window(*args, **kwargs):
        return np.zeros(128, dtype=np.float32)
    
    monkeypatch.setattr(vggish, "_vggish_embed_window", mock_embed_window)
    
    wav = np.random.randn(100).astype(np.float32)  # Very short input
    result = vggish.run_embedding_vggish(wav, sr=16000, window_sec=1.0, hop_sec=0.5, device="cpu")
    
    assert isinstance(result, np.ndarray)
    assert result.shape == (1, 128)  # Should return single window
    assert result.dtype == np.float32

def test_run_embedding_vggish_normal_windows(monkeypatch):
    """Test run_embedding_vggish with normal windowing"""
    def mock_embed_window(*args, **kwargs):
        return np.ones(128, dtype=np.float32)
    
    monkeypatch.setattr(vggish, "_vggish_embed_window", mock_embed_window)
    
    # Create 2 second audio at 16kHz
    wav = np.random.randn(32000).astype(np.float32)
    result = vggish.run_embedding_vggish(
        wav, 
        sr=16000,
        window_sec=1.0,  # 1 second windows
        hop_sec=0.5,     # 0.5 second hop
        device="cpu"
    )
    
    assert isinstance(result, np.ndarray)
    assert result.shape[1] == 128
    assert result.shape[0] > 1  # Should have multiple windows
    assert result.dtype == np.float32

def test_run_embedding_vggish_invalid_params():
    """Test run_embedding_vggish with invalid window/hop parameters"""
    wav = np.random.randn(16000).astype(np.float32)
    
    # Test with zero window size
    result = vggish.run_embedding_vggish(wav, sr=16000, window_sec=0, hop_sec=0.5, device="cpu")
    assert result.shape == (1, 128)
    
    # Test with zero hop size
    result = vggish.run_embedding_vggish(wav, sr=16000, window_sec=1.0, hop_sec=0, device="cpu")
    assert result.shape == (1, 128)

def test_run_vggish_embeddings_wrapper():
    """Test that run_vggish_embeddings correctly wraps run_embedding_vggish"""
    wav = np.random.randn(16000).astype(np.float32)
    
    with patch('backbones.vggish.run_embedding_vggish') as mock_run:
        mock_run.return_value = np.zeros((2, 128))
        result = vggish.run_vggish_embeddings(wav, sr=16000)
        
        # Verify correct default parameters
        mock_run.assert_called_once()
        called_args, called_kwargs = mock_run.call_args
        assert called_args[:4] == (wav, 16000, 2.0, 1.0)
        assert called_kwargs == {'device': 'cpu'}
        
        assert isinstance(result, np.ndarray)
        assert result.shape == (2, 128)