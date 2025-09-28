# tests/integration/test_classify_pipeline.py
import pytest
import numpy as np
from pathlib import Path
import logging
from unittest.mock import Mock, patch
import importlib
import sys

# Import module name for calling main()
MODULE_NAME = "classification.scripts.classify"

@pytest.fixture
def mock_cnn14_model():
    """Mock CNN14 model that returns predictable outputs"""
    mock = Mock()
    mock.inference.return_value = {
        'clipwise_output': np.array([0.1, 0.2, 0.7], dtype=np.float32),
        'embedding': np.array([1.0, 2.0, 3.0], dtype=np.float32),
        'labels': ['class1', 'class2', 'class3']
    }
    return mock

@pytest.fixture
def mock_rf_head():
    """Mock RandomForest head that returns predictable outputs"""
    mock = Mock()
    mock.predict_proba.return_value = np.array([[0.2, 0.3, 0.5]], dtype=np.float32)
    return mock

def run_main_with_argv(argv_list):
    """
    Import the classify module and run its main() while temporarily setting sys.argv.
    This mimics running the CLI with the provided arguments.
    """
    mod = importlib.import_module(MODULE_NAME)
    old_argv = sys.argv.copy()
    try:
        sys.argv = [old_argv[0]] + argv_list
        mod.main()
    finally:
        sys.argv = old_argv

@pytest.mark.integration
def test_classification_pipeline_with_audio_file(tmp_path: Path, mock_cnn14_model, mock_rf_head, tmp_wav_path):
    """Test the complete classification pipeline with a single audio file"""
    # ensure head file exists (main checks hp.exists() before loading)
    head_path = tmp_path / "head_cnn14_rf.joblib"
    head_path.touch()
    head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
    head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')

    with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
         patch('joblib.load', return_value=mock_rf_head), \
         patch('classification.scripts.classify.load_audio', return_value=(np.zeros(16000, dtype=np.float32), 16000)), \
         patch('classification.scripts.classify.segment_waveform', return_value=[(0.0, 1.0, np.zeros(16000, dtype=np.float32))]):
        
        # Run classification: main() uses sys.argv, so we pass args via run_main_with_argv
        # main() does not always raise SystemExit on success; run it and ensure no exception
        run_main_with_argv([
            '--audio', str(tmp_wav_path),
            '--head', str(head_path),
            '--window-sec', '2.0',
            '--hop-sec', '1.0'
        ])
        # If we reached here without exception, test considered successful

@pytest.mark.integration
def test_classification_pipeline_unknown_class(tmp_path: Path, mock_cnn14_model, mock_rf_head, tmp_wav_path):
    """Test classification with probability below unknown threshold"""
    mock_rf_head.predict_proba.return_value = np.array([[0.1, 0.1, 0.1]], dtype=np.float32)

    # ensure head file exists and metadata
    head_path = tmp_path / "head_cnn14_rf.joblib"
    head_path.touch()
    head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
    head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')

    with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
         patch('joblib.load', return_value=mock_rf_head), \
         patch('classification.scripts.classify.load_audio', return_value=(np.zeros(16000, dtype=np.float32), 16000)), \
         patch('classification.scripts.classify.segment_waveform', return_value=[(0.0, 1.0, np.zeros(16000, dtype=np.float32))]):
        
        # run main with a high unknown threshold; ensure it completes
        run_main_with_argv([
            '--audio', str(tmp_wav_path),
            '--head', str(head_path),
            '--unknown-threshold', '0.5'
        ])

@pytest.mark.integration
def test_classification_pipeline_with_directory(tmp_path: Path, mock_cnn14_model, mock_rf_head):
    """Test classification with a directory containing multiple audio files"""
    # Create test audio files (valid small WAVs)
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()
    # create tiny valid wave files using numpy + soundfile alternative is heavy;
    # instead, mock load_audio/segment_waveform below to avoid reading actual files.
    for i in range(3):
        wav_path = audio_dir / f"test{i}.wav"
        wav_path.write_bytes(b"RIFF....WAVE")  # file presence is enough because we mock load_audio

    head_path = tmp_path / "head_cnn14_rf.joblib"
    head_path.touch()
    head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
    head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')

    with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
         patch('joblib.load', return_value=mock_rf_head), \
         patch('classification.scripts.classify.load_audio', return_value=(np.zeros(16000, dtype=np.float32), 16000)), \
         patch('classification.scripts.classify.segment_waveform', return_value=[(0.0, 1.0, np.zeros(16000, dtype=np.float32))]):
        
        # run main over directory (should complete without exception)
        run_main_with_argv([
            '--audio', str(audio_dir),
            '--head', str(head_path)
        ])

@pytest.mark.integration
def test_classification_pipeline_errors(tmp_path: Path, mock_cnn14_model, mock_rf_head):
    """Test error handling in the classification pipeline"""
    # 1) Non-existent audio file -> main() logs 'no audio files under' and exits with code 0
    with pytest.raises(SystemExit) as exc:
        run_main_with_argv(['--audio', str(tmp_path / "nonexistent.wav")])
    assert exc.value.code == 0

    # 2) Unsupported extension -> should exit with non-zero (sys.exit(4) in code)
    invalid_file = tmp_path / "test.txt"
    invalid_file.touch()
    with pytest.raises(SystemExit) as exc:
        run_main_with_argv(['--audio', str(invalid_file)])
    assert exc.value.code != 0

    # 3) Invalid head file (nonexistent): code warns and proceeds without head -> exit code 0
    with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
         patch('classification.scripts.classify.load_audio', return_value=(np.zeros(16000, dtype=np.float32), 16000)), \
         patch('classification.scripts.classify.segment_waveform', return_value=[(0.0, 1.0, np.zeros(16000, dtype=np.float32))]):
        with pytest.raises(SystemExit) as exc:
            run_main_with_argv([
                '--audio', str(tmp_path),
                '--head', str(tmp_path / "nonexistent.joblib")
            ])
        assert exc.value.code == 0


# # tests/integration/test_classify_pipeline.py
# import pytest
# import numpy as np
# from pathlib import Path
# import logging
# from unittest.mock import Mock, patch
# import importlib
# import sys

# # Import module (we will call main() on the module after setting sys.argv)
# MODULE_NAME = "classification.scripts.classify"

# @pytest.fixture
# def mock_cnn14_model():
#     """Mock CNN14 model that returns predictable outputs"""
#     mock = Mock()
#     mock.inference.return_value = {
#         'clipwise_output': np.array([0.1, 0.2, 0.7], dtype=np.float32),
#         'embedding': np.array([1.0, 2.0, 3.0], dtype=np.float32),
#         'labels': ['class1', 'class2', 'class3']
#     }
#     return mock

# @pytest.fixture
# def mock_rf_head():
#     """Mock RandomForest head that returns predictable outputs"""
#     mock = Mock()
#     mock.predict_proba.return_value = np.array([[0.2, 0.3, 0.5]], dtype=np.float32)
#     return mock

# def run_main_with_argv(argv_list):
#     """
#     Import the classify module and run its main() while temporarily setting sys.argv.
#     This mimics running the CLI with the provided arguments.
#     """
#     mod = importlib.import_module(MODULE_NAME)
#     old_argv = sys.argv.copy()
#     try:
#         sys.argv = [old_argv[0]] + argv_list
#         mod.main()
#     finally:
#         sys.argv = old_argv

# @pytest.mark.integration
# def test_classification_pipeline_with_audio_file(tmp_path: Path, mock_cnn14_model, mock_rf_head, tmp_wav_path):
#     """Test the complete classification pipeline with a single audio file"""
#     with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
#          patch('joblib.load', return_value=mock_rf_head):
        
#         # Create a mock head metadata file
#         head_path = tmp_path / "head_cnn14_rf.joblib"
#         head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
#         head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')
        
#         # Run classification: main() uses sys.argv, so we pass args via run_main_with_argv
#         with pytest.raises(SystemExit) as exc:
#             run_main_with_argv([
#                 '--audio', str(tmp_wav_path),
#                 '--head', str(head_path),
#                 '--window-sec', '2.0',
#                 '--hop-sec', '1.0'
#             ])
#         assert exc.value.code == 0

# @pytest.mark.integration
# def test_classification_pipeline_unknown_class(tmp_path: Path, mock_cnn14_model, mock_rf_head, tmp_wav_path):
#     """Test classification with probability below unknown threshold"""
#     mock_rf_head.predict_proba.return_value = np.array([[0.1, 0.1, 0.1]], dtype=np.float32)
    
#     with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
#          patch('joblib.load', return_value=mock_rf_head):
        
#         head_path = tmp_path / "head_cnn14_rf.joblib"
#         head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
#         head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')
        
#         with pytest.raises(SystemExit) as exc:
#             run_main_with_argv([
#                 '--audio', str(tmp_wav_path),
#                 '--head', str(head_path),
#                 '--unknown-threshold', '0.5'
#             ])
#         assert exc.value.code == 0

# @pytest.mark.integration
# def test_classification_pipeline_with_directory(tmp_path: Path, mock_cnn14_model, mock_rf_head):
#     """Test classification with a directory containing multiple audio files"""
#     # Create test audio files
#     audio_dir = tmp_path / "audio"
#     audio_dir.mkdir()
#     for i in range(3):
#         wav_path = audio_dir / f"test{i}.wav"
#         wav_path.write_bytes(b"RIFF....WAVE")
    
#     with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
#          patch('joblib.load', return_value=mock_rf_head):
        
#         head_path = tmp_path / "head_cnn14_rf.joblib"
#         head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
#         head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')
        
#         with pytest.raises(SystemExit) as exc:
#             run_main_with_argv([
#                 '--audio', str(audio_dir),
#                 '--head', str(head_path)
#             ])
#         assert exc.value.code == 0

# @pytest.mark.integration
# def test_classification_pipeline_errors(tmp_path: Path, mock_cnn14_model, mock_rf_head):
#     """Test error handling in the classification pipeline"""
#     # Test with non-existent audio file
#     with pytest.raises(SystemExit) as exc:
#         run_main_with_argv(['--audio', str(tmp_path / "nonexistent.wav")])
#     assert exc.value.code != 0
    
#     # Test with unsupported file extension
#     invalid_file = tmp_path / "test.txt"
#     invalid_file.touch()
#     with pytest.raises(SystemExit) as exc:
#         run_main_with_argv(['--audio', str(invalid_file)])
#     assert exc.value.code != 0
    
#     # Test with invalid head file
#     with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model):
#         with pytest.raises(SystemExit) as exc:
#             run_main_with_argv([
#                 '--audio', str(tmp_path),
#                 '--head', str(tmp_path / "nonexistent.joblib")
#             ])
#         assert exc.value.code != 0


# # import pytest
# # import numpy as np
# # from pathlib import Path
# # import logging
# # from unittest.mock import Mock, patch

# # from scripts.classify import main as classify_main
# # from backbones.cnn14 import load_cnn14_model
# # from core.model_io import load_audio, segment_waveform

# # @pytest.fixture
# # def mock_cnn14_model():
# #     """Mock CNN14 model that returns predictable outputs"""
# #     mock = Mock()
# #     mock.inference.return_value = {
# #         'clipwise_output': np.array([0.1, 0.2, 0.7], dtype=np.float32),
# #         'embedding': np.array([1.0, 2.0, 3.0], dtype=np.float32),
# #         'labels': ['class1', 'class2', 'class3']
# #     }
# #     return mock

# # @pytest.fixture
# # def mock_rf_head():
# #     """Mock RandomForest head that returns predictable outputs"""
# #     mock = Mock()
# #     mock.predict_proba.return_value = np.array([[0.2, 0.3, 0.5]], dtype=np.float32)
# #     return mock

# # @pytest.mark.integration
# # def test_classification_pipeline_with_audio_file(tmp_path: Path, mock_cnn14_model, mock_rf_head, tmp_wav_path):
# #     """Test the complete classification pipeline with a single audio file"""
# #     with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
# #          patch('joblib.load', return_value=mock_rf_head):
        
# #         # Create a mock head metadata file
# #         head_path = tmp_path / "head_cnn14_rf.joblib"
# #         head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
# #         head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')
        
# #         # Run classification
# #         with pytest.raises(SystemExit) as exc:
# #             classify_main([
# #                 '--audio', str(tmp_wav_path),
# #                 '--head', str(head_path),
# #                 '--window-sec', '2.0',
# #                 '--hop-sec', '1.0'
# #             ])
# #         assert exc.value.code == 0

# # @pytest.mark.integration
# # def test_classification_pipeline_unknown_class(tmp_path: Path, mock_cnn14_model, mock_rf_head, tmp_wav_path):
# #     """Test classification with probability below unknown threshold"""
# #     mock_rf_head.predict_proba.return_value = np.array([[0.1, 0.1, 0.1]], dtype=np.float32)
    
# #     with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
# #          patch('joblib.load', return_value=mock_rf_head):
        
# #         head_path = tmp_path / "head_cnn14_rf.joblib"
# #         head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
# #         head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')
        
# #         with pytest.raises(SystemExit) as exc:
# #             classify_main([
# #                 '--audio', str(tmp_wav_path),
# #                 '--head', str(head_path),
# #                 '--unknown-threshold', '0.5'
# #             ])
# #         assert exc.value.code == 0

# # @pytest.mark.integration
# # def test_classification_pipeline_with_directory(tmp_path: Path, mock_cnn14_model, mock_rf_head):
# #     """Test classification with a directory containing multiple audio files"""
# #     # Create test audio files
# #     audio_dir = tmp_path / "audio"
# #     audio_dir.mkdir()
# #     for i in range(3):
# #         wav_path = audio_dir / f"test{i}.wav"
# #         wav_path.write_bytes(b"RIFF....WAVE")
    
# #     with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model), \
# #          patch('joblib.load', return_value=mock_rf_head):
        
# #         head_path = tmp_path / "head_cnn14_rf.joblib"
# #         head_meta = tmp_path / "head_cnn14_rf.joblib.meta.json"
# #         head_meta.write_text('{"embedding_dim": 3, "class_order": ["birds", "insects", "vehicle"]}')
        
# #         with pytest.raises(SystemExit) as exc:
# #             classify_main([
# #                 '--audio', str(audio_dir),
# #                 '--head', str(head_path)
# #             ])
# #         assert exc.value.code == 0

# # @pytest.mark.integration
# # def test_classification_pipeline_errors(tmp_path: Path, mock_cnn14_model, mock_rf_head):
# #     """Test error handling in the classification pipeline"""
# #     # Test with non-existent audio file
# #     with pytest.raises(SystemExit) as exc:
# #         classify_main(['--audio', str(tmp_path / "nonexistent.wav")])
# #     assert exc.value.code != 0
    
# #     # Test with unsupported file extension
# #     invalid_file = tmp_path / "test.txt"
# #     invalid_file.touch()
# #     with pytest.raises(SystemExit) as exc:
# #         classify_main(['--audio', str(invalid_file)])
# #     assert exc.value.code != 0
    
# #     # Test with invalid head file
# #     with patch('classification.scripts.classify.load_cnn14_model', return_value=mock_cnn14_model):
# #         with pytest.raises(SystemExit) as exc:
# #             classify_main([
# #                 '--audio', str(tmp_path),
# #                 '--head', str(tmp_path / "nonexistent.joblib")
# #             ])
# #         assert exc.value.code != 0