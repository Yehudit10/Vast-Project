import pytest
import numpy as np
import torch
from backbones import ast
import os
from pathlib import Path

def test_resample_to_target():
    """Test _resample_to_target function with different scenarios"""
    # Test when target sr equals input sr
    wav = np.ones(16000, dtype=np.float32)
    result = ast._resample_to_target(wav, sr=16000, target_sr=16000)
    assert result.dtype == np.float32
    assert len(result) == 16000
    assert np.array_equal(result, wav)
    
    # Test resampling to higher sr
    wav = np.ones(8000, dtype=np.float32)
    result = ast._resample_to_target(wav, sr=8000, target_sr=16000)
    assert result.dtype == np.float32
    assert len(result) == 16000
    
    # Test resampling to lower sr
    wav = np.ones(16000, dtype=np.float32)
    result = ast._resample_to_target(wav, sr=16000, target_sr=8000)
    assert result.dtype == np.float32
    assert len(result) == 8000

def test_load_ast_components(tmp_path, monkeypatch):
    """Test _load_ast_components function with mocked transformers"""
    model_path = tmp_path / "ast_model"
    model_path.mkdir()
    
    # Create mock feature extractor and model classes
    class MockFeatureExtractor:
        def __call__(self, *args, **kwargs):
            return {"input_values": torch.ones(1, 1000)}
    
    class MockModel:
        def __init__(self):
            self.device = "cpu"
            
        def to(self, device):
            self.device = device
            return self
            
        def eval(self):
            pass
    
    def mock_from_pretrained_fe(*args, **kwargs):
        return MockFeatureExtractor()
        
    def mock_from_pretrained_model(*args, **kwargs):
        return MockModel()
    
    monkeypatch.setattr(ast.AutoFeatureExtractor, "from_pretrained", mock_from_pretrained_fe)
    monkeypatch.setattr(ast.AutoModelForAudioClassification, "from_pretrained", mock_from_pretrained_model)
    
    # Test loading components
    fe, model = ast._load_ast_components(str(model_path), "cpu")
    assert isinstance(fe, MockFeatureExtractor)
    assert isinstance(model, MockModel)
    assert model.device == "cpu"

@pytest.mark.parametrize("device", ["cpu", "cuda"])
def test_run_embedding_ast(tmp_path, monkeypatch, device):
    """Test run_embedding_ast function with mocked components"""
    # Skip CUDA case if CUDA is not available in this environment
    if device == "cuda" and not torch.cuda.is_available():
        pytest.skip("CUDA not available in this environment")

    model_path = tmp_path / "ast_model"
    model_path.mkdir()
    
    # Create mock outputs
    class MockHiddenStates:
        def __init__(self):
            self.hidden_states = [torch.ones(1, 10, 768)]  # Mock last hidden state
    
    class MockFeatureExtractor:
        def __call__(self, *args, **kwargs):
            return {"input_values": torch.ones(1, 1000)}
    
    class MockModel:
        def __init__(self):
            self.device = device
            
        def to(self, device):
            self.device = device
            return self
            
        def eval(self):
            pass
            
        def __call__(self, **kwargs):
            return MockHiddenStates()
    
    def mock_from_pretrained_fe(*args, **kwargs):
        return MockFeatureExtractor()
        
    def mock_from_pretrained_model(*args, **kwargs):
        return MockModel()
    
    monkeypatch.setattr(ast.AutoFeatureExtractor, "from_pretrained", mock_from_pretrained_fe)
    monkeypatch.setattr(ast.AutoModelForAudioClassification, "from_pretrained", mock_from_pretrained_model)
    
    # Test with different sampling rates
    wav = np.ones(16000, dtype=np.float32)
    
    # Test with matching sampling rate
    emb = ast.run_embedding_ast(wav, sr=16000, device=device, model_path=str(model_path))
    assert isinstance(emb, np.ndarray)
    assert emb.dtype == np.float32
    assert emb.shape == (768,)  # AST typically outputs 768-dim embeddings
    
    # Test with different sampling rate
    emb = ast.run_embedding_ast(wav, sr=8000, device=device, model_path=str(model_path))
    assert isinstance(emb, np.ndarray)
    assert emb.dtype == np.float32
    assert emb.shape == (768,)

def test_run_ast_embedding(tmp_path, monkeypatch):
    """Test run_ast_embedding function (wrapper for run_embedding_ast)"""
    # Since run_ast_embedding is just a wrapper, we can do a simple test
    model_path = tmp_path / "ast_model"
    model_path.mkdir()
    
    calls = []
    def mock_run_embedding_ast(*args, **kwargs):
        calls.append(kwargs)
        return np.zeros(768, dtype=np.float32)
    
    monkeypatch.setattr(ast, "run_embedding_ast", mock_run_embedding_ast)
    
    wav = np.ones(16000, dtype=np.float32)
    emb = ast.run_ast_embedding(wav, sr=16000, device="cpu", model_path=str(model_path))
    
    assert len(calls) == 1
    assert calls[0]["sr"] == 16000
    assert calls[0]["device"] == "cpu"
    assert calls[0]["model_path"] == str(model_path)
    assert isinstance(emb, np.ndarray)
    assert emb.shape == (768,)
    assert emb.dtype == np.float32

def test_error_cases(monkeypatch):
    """Test error cases and edge conditions"""
    # Test missing model path
    with pytest.raises(RuntimeError):
        ast.run_embedding_ast(np.zeros(1000), sr=16000, device="cpu", model_path=None)
    
    # Test with backward compatibility ast_model_dir parameter
    wav = np.zeros(1000, dtype=np.float32)
    with pytest.raises(RuntimeError):
        ast.run_embedding_ast(wav, sr=16000, device="cpu", ast_model_dir=None)
        
    # For the non-numpy input case, mock out the model/component loading
    # so we don't try to hit the real transformers code in the test.
    class MockHiddenStates:
        def __init__(self):
            self.hidden_states = [torch.ones(1, 10, 768)]
    class MockFeatureExtractor:
        def __call__(self, *args, **kwargs):
            return {"input_values": torch.ones(1, 1000)}
    class MockModel:
        def __init__(self):
            self.device = "cpu"
        def to(self, device):
            self.device = device
            return self
        def eval(self):
            pass
        def __call__(self, **kwargs):
            return MockHiddenStates()

    # Monkeypatch the component loader to return mocks
    monkeypatch.setattr(ast, "_load_ast_components", lambda model_path, device: (MockFeatureExtractor(), MockModel()))
        
    # Now calling with a plain Python list should raise an exception (invalid input)
    with pytest.raises(Exception):
        ast.run_embedding_ast([1, 2, 3], sr=16000, device="cpu", model_path="dummy")
