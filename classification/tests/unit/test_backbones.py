# tests/unit/test_backbones.py
import pytest
import numpy as np
import torch
from pathlib import Path
from unittest.mock import Mock, patch

from classification.backbones.cnn14 import load_cnn14_model, run_cnn14_embedding
from classification.backbones.vggish import run_vggish_embeddings
from classification.backbones.ast import run_ast_embedding

@pytest.fixture
def mock_torch_hub():
    """Mock torch.hub.load for CNN14 testing"""
    mock = Mock()
    mock.to.return_value = mock
    mock.eval.return_value = mock
    mock.inference.return_value = {
        'clipwise_output': torch.tensor([0.1, 0.2, 0.3]),
        'embedding': torch.tensor([1.0, 2.0, 3.0])
    }
    return mock

@pytest.mark.backbone
def test_load_cnn14_model(mock_torch_hub, tmp_path):
    """Test CNN14 model loading with various configurations"""
    checkpoint = tmp_path / "Cnn14_mAP=0.431.pth"
    checkpoint.touch()
    
    with patch('classification.backbones.cnn14.AudioTagging', return_value=mock_torch_hub):
        # Test with local checkpoint
        model = load_cnn14_model(str(checkpoint))
        assert model is not None
        
        # Test with URL checkpoint
        model = load_cnn14_model(None, checkpoint_url="http://example.com/model.pth")
        assert model is not None
        
        # Test with device specification
        model = load_cnn14_model(str(checkpoint), device="cuda")
        assert model is not None

@pytest.mark.backbone
def test_run_cnn14_embedding(mock_torch_hub, tmp_wav_path):
    """Test CNN14 embedding generation"""
    with patch('classification.backbones.cnn14.AudioTagging', return_value=mock_torch_hub):
        model = load_cnn14_model(None, checkpoint_url="http://example.com/model.pth")
        
        # Test with valid input
        waveform = np.random.randn(16000)
        emb = run_cnn14_embedding(model, waveform)
        assert isinstance(emb, np.ndarray)
        assert emb.shape == (3,)
        
        # Test with invalid input (empty waveform)
        with pytest.raises(ValueError):
            run_cnn14_embedding(model, np.zeros(0))

@pytest.mark.backbone
def test_run_vggish_embeddings(tmp_wav_path):
    """Test VGGish embedding generation"""
    with patch('soundfile.read', return_value=(np.random.randn(16000), 16000)):
        embeddings = run_vggish_embeddings(
            np.random.randn(16000), 16000,
            window_sec=1.0,
            hop_sec=1.0,
            device="cpu"
        )
        assert isinstance(embeddings, np.ndarray)
        assert embeddings.ndim == 2
        assert embeddings.shape[1] == 128
        
        embeddings = run_vggish_embeddings(
            np.random.randn(32000), 16000,
            window_sec=0.5,
            hop_sec=0.25,
            device="cpu"
        )
        assert embeddings.shape[0] > 1

@pytest.mark.backbone
def test_run_ast_embedding(tmp_wav_path):
    """Test AST embedding generation using mocks to avoid downloading real models"""
    # Prepare mocks for feature extractor and model loader
    fe_mock = Mock()
    fe_mock.return_value = {"input_values": torch.randn(1, 16000)}

    model_mock = Mock()
    model_mock.device = torch.device("cpu")
    
    fake_last = torch.randn(1, 10, 768)
    out = Mock()
    out.hidden_states = [torch.randn(1, 10, 768) for _ in range(3)]
    out.hidden_states[-1] = fake_last
    model_mock.return_value = out

    # Patch the internal loader at the correct import path
    with patch('classification.backbones.ast._load_ast_components', return_value=(fe_mock, model_mock)):
        emb = run_ast_embedding(
            np.random.randn(16000),
            sr=16000,
            device="cpu",
            model_path=str(tmp_wav_path.parent),
            local_only=True
        )
        assert isinstance(emb, np.ndarray)
        assert emb.shape == (768,)

@pytest.mark.backbone
def test_backbone_error_handling():
    """Test error handling in backbone models"""
    # CNN14 with invalid checkpoint
    with pytest.raises(Exception):
        load_cnn14_model("nonexistent.pth")
    
    # VGGish with empty waveform
    with pytest.raises(ValueError):
        run_vggish_embeddings(np.zeros(0), 16000)
    
    # AST with invalid model path
    with pytest.raises(Exception):
        run_ast_embedding(
            np.random.randn(16000),
            sr=16000,
            model_path="nonexistent",
            local_only=True
        )
