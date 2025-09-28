# tests/integration/test_pipeline.py
import pytest
import tempfile
from pathlib import Path
import numpy as np
import soundfile as sf
from unittest.mock import patch, Mock
import importlib
import sys

# -----------------------------
# Fixture: Temporary mock audio files
# -----------------------------
@pytest.fixture
def mock_audio_files():
    """Create temporary WAV files (1s silent @16k) for integration-like tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        files = []
        for i in range(3):
            wav_path = tmp_path / f"file_{i}.wav"
            # Generate 1 second of silent audio at 16kHz
            wav_data = np.zeros(16000, dtype=np.float32)
            sf.write(str(wav_path), wav_data, samplerate=16000)
            files.append(wav_path)
        yield files

# -----------------------------
# Fixture: Mock CNN14 / AudioTagging model
# -----------------------------
@pytest.fixture
def mock_audio_tagging_model():
    """Mock out the CNN14 loader to return a simple deterministic mock model."""
    with patch("classification.backbones.cnn14.load_cnn14_model") as mock_load:
        model = Mock()
        model.to.return_value = model
        model.eval.return_value = model
        # deterministic embedding for tests (128-d)
        model.inference.return_value = {"embedding": np.ones(128)}
        mock_load.return_value = model
        yield mock_load

# -----------------------------
# Fixture: Mock heavy functions in classify and DB IO
# -----------------------------
@pytest.fixture(autouse=True)
def mock_heavy_dependencies():
    """
    Patch heavy or external dependencies used by the classify pipeline so the integration-like
    test runs fast and deterministic without network / heavy models / DB.
    """
    with patch("classification.scripts.classify.ensure_checkpoint") as mock_checkpoint, \
         patch("classification.scripts.classify.load_audio") as mock_load_audio, \
         patch("classification.scripts.classify.segment_waveform") as mock_segment, \
         patch("classification.core.model_io.run_inference") as mock_inference, \
         patch("classification.core.model_io.run_inference_with_embedding") as mock_emb, \
         patch("classification.scripts.classify.aggregate_matrix") as mock_aggregate, \
         patch("core.db_io_pg.open_db") as mock_open_db, \
         patch("core.db_io_pg.upsert_run") as mock_upsert_run, \
         patch("core.db_io_pg.upsert_file") as mock_upsert_file, \
         patch("core.db_io_pg.upsert_file_aggregate") as mock_upsert_file_aggregate, \
         patch("core.db_io_pg.finish_run") as mock_finish_run:
        # checkpoint returns local path
        mock_checkpoint.return_value = "/tmp/mock_checkpoint"
        
        # load_audio returns synthetic waveform and sample rate
        mock_load_audio.return_value = (np.zeros(16000, dtype=np.float32), 16000)
        
        # segment_waveform returns one segment with time window values
        # emulate windows as list of tuples: (t0, t1, segment_array)
        mock_segment.return_value = [(0.0, 1.0, np.zeros(16000, dtype=np.float32))]
        
        # inference returns deterministic prediction (per-window probs)
        mock_inference.return_value = np.array([0.1, 0.9])
        # run_inference_with_embedding returns (embedding, probs)
        mock_emb.return_value = (np.ones(128), np.array([0.1, 0.9]))
        
        # aggregate_matrix returns a fixed array (e.g., aggregated probs)
        mock_aggregate.return_value = np.array([0.1, 0.9])
        
        # DB mocks: open_db returns a dummy connection object
        mock_open_db.return_value = Mock()
        mock_upsert_run.return_value = None
        mock_upsert_file.return_value = 123  # fake file_id
        mock_upsert_file_aggregate.return_value = None
        mock_finish_run.return_value = None
        
        yield

# -----------------------------
# Helper: run classify.main() by simulating CLI args
# -----------------------------
def run_classify_main_with_args(args_list):
    """
    Import classification.scripts.classify and run its main() with argv mocked to args_list.
    This function will raise exceptions from main() if something goes wrong.
    """
    mod = importlib.import_module("classification.scripts.classify")
    old_argv = sys.argv.copy()
    try:
        sys.argv = [old_argv[0]] + args_list
        # Execute main() — it uses argparse and sys.argv internally
        mod.main()
    finally:
        sys.argv = old_argv

# -----------------------------
# Integration-like test: classify CLI
# -----------------------------
def test_classify_cli(mock_audio_files, mock_audio_tagging_model):
    """Integration-like test for classify pipeline (no DB) - ensures main() runs end-to-end without error."""
    audio_dir = str(Path(mock_audio_files[0]).parent)
    args = [
        "--audio", audio_dir,
        "--backbone", "cnn14",
        "--device", "cpu",
        "--window-sec", "1.0",
        "--hop-sec", "1.0",
        # no --write-db to avoid DB path
    ]
    # This should complete without raising an exception
    run_classify_main_with_args(args)

# -----------------------------
# Optional test: DB write (mocked)
# -----------------------------
def test_classify_cli_with_db(mock_audio_files, mock_audio_tagging_model):
    """Integration-like test for classify pipeline that includes DB write path (DB operations mocked)."""
    audio_dir = str(Path(mock_audio_files[0]).parent)
    args = [
        "--audio", audio_dir,
        "--backbone", "cnn14",
        "--device", "cpu",
        "--window-sec", "1.0",
        "--hop-sec", "1.0",
        "--write-db",
        "--db-url", "postgresql://user:pw@localhost/db"  # value won't be used because open_db is mocked
    ]
    # This should complete without raising an exception (DB functions are mocked)
    run_classify_main_with_args(args)


# # tests/integration/test_pipeline.py
# import pytest
# import tempfile
# from pathlib import Path
# import numpy as np
# import soundfile as sf
# from unittest.mock import patch, Mock
# import importlib

# # -----------------------------
# # Fixture: Temporary mock audio files
# # -----------------------------
# @pytest.fixture
# def mock_audio_files():
#     """Create temporary WAV files (1s silent @16k) for integration-like tests."""
#     with tempfile.TemporaryDirectory() as tmpdir:
#         tmp_path = Path(tmpdir)
#         files = []
#         for i in range(3):
#             wav_path = tmp_path / f"file_{i}.wav"
#             # Generate 1 second of silent audio at 16kHz
#             wav_data = np.zeros(16000, dtype=np.float32)
#             sf.write(str(wav_path), wav_data, samplerate=16000)
#             files.append(wav_path)
#         yield files

# # -----------------------------
# # Fixture: Mock CNN14 / AudioTagging model
# # -----------------------------
# @pytest.fixture
# def mock_audio_tagging_model():
#     """Mock out the CNN14 loader to return a simple deterministic mock model."""
#     with patch("classification.backbones.cnn14.load_cnn14_model") as mock_load:
#         model = Mock()
#         model.to.return_value = model
#         model.eval.return_value = model
#         # deterministic embedding for tests (128-d)
#         model.inference.return_value = {"embedding": np.ones(128)}
#         mock_load.return_value = model
#         yield mock_load

# # -----------------------------
# # Fixture: Mock heavy functions in classify
# # -----------------------------
# @pytest.fixture(autouse=True)
# def mock_heavy_dependencies():
#     """
#     Patch heavy or external dependencies used by the classify pipeline so the integration-like
#     test runs fast and deterministic without network / heavy models / DB.
#     """
#     with patch("classification.scripts.classify.ensure_checkpoint") as mock_checkpoint, \
#          patch("classification.scripts.classify.load_audio") as mock_load_audio, \
#          patch("classification.scripts.classify.segment_waveform") as mock_segment, \
#          patch("classification.core.model_io.run_inference") as mock_inference, \
#          patch("classification.core.model_io.run_inference_with_embedding") as mock_emb, \
#          patch("classification.scripts.classify.aggregate_matrix") as mock_aggregate:
#         # checkpoint returns local path
#         mock_checkpoint.return_value = "/tmp/mock_checkpoint"
        
#         # load_audio returns synthetic waveform and sample rate
#         mock_load_audio.return_value = (np.zeros(16000, dtype=np.float32), 16000)
        
#         # segment_waveform returns one segment
#         mock_segment.return_value = [np.zeros(16000, dtype=np.float32)]
        
#         # inference returns deterministic prediction
#         mock_inference.return_value = np.array([0.1, 0.9])
#         mock_emb.return_value = (np.ones(128), np.array([0.1, 0.9]))
        
#         # aggregate_matrix returns a fixed array
#         mock_aggregate.return_value = np.array([0.1, 0.9])
        
#         yield

# # -----------------------------
# # Helper: robust importer for classify_files
# # -----------------------------
# def import_classify_files():
#     """
#     Try to import `classify_files` from the package. If direct import fails,
#     import the module and try to locate an appropriate function name.
#     """
#     try:
#         # Prefer direct import if available
#         from classification.scripts.classify import classify_files
#         return classify_files
#     except Exception:
#         # Attempt robust fallback: import module and search for likely function names
#         mod = importlib.import_module("classification.scripts.classify")
#         for candidate in ("classify_files", "classify", "main", "run", "process_files"):
#             if hasattr(mod, candidate):
#                 return getattr(mod, candidate)
#         # If nothing found, re-raise a clear ImportError
#         raise ImportError("Could not find a classify function in classification.scripts.classify. "
#                           "Expected 'classify_files' or one of ('classify','main','run','process_files').")

# # -----------------------------
# # Integration-like test: classify CLI
# # -----------------------------
# def test_classify_cli(mock_audio_files, mock_audio_tagging_model):
#     """Integration-like test for classify pipeline (no DB) - ensures outputs have expected structure."""
#     classify_fn = import_classify_files()
    
#     results = classify_fn(
#         audio_paths=[str(f) for f in mock_audio_files],
#         backbone="cnn14",
#         device="cpu",
#         write_db=False
#     )
    
#     # Check structure of results
#     for res in results:
#         assert "file_path" in res
#         assert "predictions" in res
#         # predictions is array-like and matches mocked inference
#         np.testing.assert_almost_equal(np.asarray(res["predictions"]), np.array([0.1, 0.9]))

# # -----------------------------
# # Optional test: DB write (mocked)
# # -----------------------------
# def test_classify_cli_with_db(mock_audio_files, mock_audio_tagging_model):
#     """Integration-like test for classify pipeline that includes DB write path (DB operations mocked)."""
#     classify_fn = import_classify_files()
    
#     results = classify_fn(
#         audio_paths=[str(f) for f in mock_audio_files],
#         backbone="cnn14",
#         device="cpu",
#         write_db=True
#     )
    
#     # results structure
#     for res in results:
#         assert "file_path" in res
#         assert "predictions" in res



# # # classification/tests/integration/test_classify_cli.py
# # import pytest
# # import tempfile
# # from pathlib import Path
# # import numpy as np
# # import soundfile as sf
# # from unittest.mock import patch, Mock

# # # -----------------------------
# # # Fixture: Temporary mock audio files
# # # -----------------------------
# # @pytest.fixture
# # def mock_audio_files():
# #     with tempfile.TemporaryDirectory() as tmpdir:
# #         tmp_path = Path(tmpdir)
# #         files = []
# #         for i in range(3):
# #             wav_path = tmp_path / f"file_{i}.wav"
# #             # Generate 1 second of silent audio at 16kHz
# #             wav_data = np.zeros(16000, dtype=np.float32)
# #             sf.write(str(wav_path), wav_data, samplerate=16000)
# #             files.append(wav_path)
# #         yield files

# # # -----------------------------
# # # Fixture: Mock CNN14 / AudioTagging model
# # # -----------------------------
# # @pytest.fixture
# # def mock_audio_tagging_model():
# #     with patch("backbones.cnn14.load_cnn14_model") as mock_load:
# #         model = Mock()
# #         model.to.return_value = model
# #         model.eval.return_value = model
# #         # deterministic embedding for tests
# #         model.inference.return_value = {"embedding": np.ones(128)}
# #         mock_load.return_value = model
# #         yield mock_load

# # # -----------------------------
# # # Fixture: Mock heavy functions in classify
# # # -----------------------------
# # @pytest.fixture(autouse=True)
# # def mock_heavy_dependencies():
# #     with patch("scripts.classify.ensure_checkpoint") as mock_checkpoint, \
# #          patch("scripts.classify.load_audio") as mock_load_audio, \
# #          patch("scripts.classify.segment_waveform") as mock_segment, \
# #          patch("core.model_io.run_inference") as mock_inference, \
# #          patch("core.model_io.run_inference_with_embedding") as mock_emb, \
# #          patch("scripts.classify.aggregate_matrix") as mock_aggregate:
# #         #  patch("scripts.classify.Job") as mock_job:
        
# #         # checkpoint returns local path
# #         mock_checkpoint.return_value = "/tmp/mock_checkpoint"
        
# #         # load_audio returns synthetic waveform and sample rate
# #         mock_load_audio.return_value = (np.zeros(16000, dtype=np.float32), 16000)
        
# #         # segment_waveform returns one segment
# #         mock_segment.return_value = [np.zeros(16000, dtype=np.float32)]
        
# #         # inference returns deterministic prediction
# #         mock_inference.return_value = np.array([0.1, 0.9])
# #         mock_emb.return_value = (np.ones(128), np.array([0.1, 0.9]))
        
# #         # aggregate_matrix returns a fixed array
# #         mock_aggregate.return_value = np.array([0.1, 0.9])
        
# #         # Job mocking
# #         # mock_job_instance = Mock()
# #         # mock_job.return_value = mock_job_instance
# #         # mock_job_instance.enqueue.return_value = None
        
# #         yield

# # # -----------------------------
# # # Integration-like test: classify CLI
# # # -----------------------------
# # def test_classify_cli(mock_audio_files, mock_audio_tagging_model):
# #     from classification.scripts.classify import classify_files
    
# #     results = classify_files(
# #         audio_paths=[str(f) for f in mock_audio_files],
# #         backbone="cnn14",
# #         device="cpu",
# #         write_db=False
# #     )
    
# #     # Check structure of results
# #     for res in results:
# #         assert "file_path" in res
# #         assert "predictions" in res
# #         # predictions is array-like
# #         np.testing.assert_almost_equal(res["predictions"], np.array([0.1, 0.9]))

# # # -----------------------------
# # # Optional test: DB write (mocked)
# # # -----------------------------
# # def test_classify_cli_with_db(mock_audio_files, mock_audio_tagging_model):
# #     from classification.scripts.classify import classify_files
    
# #     results = classify_files(
# #         audio_paths=[str(f) for f in mock_audio_files],
# #         backbone="cnn14",
# #         device="cpu",
# #         write_db=True
# #     )
    
# #     # results structure
# #     for res in results:
# #         assert "file_path" in res
# #         assert "predictions" in res


# # # import tempfile
# # # import pytest
# # # import numpy as np
# # # import torch
# # # from pathlib import Path
# # # from unittest.mock import Mock, patch
# # # import soundfile as sf

# # # from backbones.cnn14 import load_cnn14_model, run_cnn14_embedding
# # # from core.model_io import SAMPLE_RATE, load_audio, ensure_numpy_1d, run_inference
# # # from head import build_head_pipeline


# # # def train_head_from_dir(audio_dir, output_dir, backbone='cnn14', head_type='rf', batch_size=32, device='cpu'):
# # #     """Helper function to train a head from an audio directory"""
# # #     # Load CNN14 model
# # #     at = load_cnn14_model(device=device) if backbone == 'cnn14' else None
    
# # #     # Get class names from directory structure
# # #     audio_dir = Path(audio_dir)
# # #     class_names = [d.name for d in audio_dir.iterdir() if d.is_dir()]
    
# # #     # Collect all audio files
# # #     pairs = []
# # #     for cls in class_names:
# # #         d = audio_dir / cls
# # #         for p in d.rglob("*"):
# # #             if p.is_file() and p.suffix.lower() in ['.wav', '.mp3', '.flac', '.m4a', '.ogg']:
# # #                 pairs.append((cls, p))
    
# # #     if not pairs:
# # #         raise ValueError(f"No audio files found in {audio_dir}")
    
# # #     # Extract embeddings
# # #     X, y = [], []
# # #     for lbl, path in pairs:
# # #         try:
# # #             wav = load_audio(str(path), target_sr=SAMPLE_RATE)
# # #             wav = ensure_numpy_1d(wav)
# # #             if backbone == 'cnn14':
# # #                 emb = run_cnn14_embedding(at, wav)
# # #             else:
# # #                 raise ValueError(f"Unsupported backbone: {backbone}")
# # #             X.append(emb)
# # #             y.append(class_names.index(lbl))
# # #         except Exception as e:
# # #             print(f"[warn] skipped {path}: {e}")
# # #             continue
    
# # #     if not X:
# # #         raise ValueError("Failed to extract any embeddings")
    
# # #     # Convert to numpy arrays
# # #     X = np.stack(X, axis=0)
# # #     y = np.array(y)
    
# # #     # Train head
# # #     pipe = build_head_pipeline(seed=42)
# # #     pipe.fit(X, y)
    
# # #     # Save model and metadata
# # #     output_dir = Path(output_dir)
# # #     output_dir.mkdir(parents=True, exist_ok=True)
# # #     model_path = output_dir / f"head_{backbone}_{head_type}.joblib"
    
# # #     import joblib
# # #     import json
# # #     joblib.dump(pipe, model_path)
    
# # #     meta = {
# # #         "class_order": class_names,
# # #         "head_type": head_type,
# # #         "backbone": backbone,
# # #         "embedding_dim": X.shape[1],
# # #     }
# # #     meta_path = model_path.with_suffix(model_path.suffix + ".meta.json")
# # #     meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    
# # #     return str(model_path)

# # # @pytest.fixture
# # # def mock_audio_files():
# # #     with tempfile.TemporaryDirectory() as tmpdir:
# # #         tmp_path = Path(tmpdir)
# # #         files = []
# # #         for i in range(3):
# # #             wav_path = tmp_path / f"file_{i}.wav"
# # #             # יצירת 1 שניה של אודיו דומם ב-16kHz
# # #             wav_data = np.zeros(16000, dtype=np.float32)
# # #             sf.write(str(wav_path), wav_data, samplerate=16000)
# # #             files.append(wav_path)
# # #         yield files

# # # @pytest.fixture
# # # def mock_cnn14_model():
# # #     with patch("backbones.cnn14.load_cnn14_model") as mock_load:
# # #         mock_at = Mock()
# # #         mock_at.to.return_value = mock_at
# # #         mock_at.eval.return_value = mock_at
# # #         mock_at.inference.return_value = {"embedding": np.ones(128)}
# # #         mock_load.return_value = mock_at
# # #         yield mock_load

# # # @pytest.fixture
# # # def mock_cnn14():
# # #     """Mock CNN14 model with predictable outputs"""
# # #     mock = Mock()
# # #     mock.to.return_value = mock
# # #     mock.eval.return_value = mock
    
# # #     def inference(wav):
# # #         return {
# # #             'clipwise_output': torch.tensor([0.3, 0.4, 0.3]),
# # #             'embedding': torch.randn(128),
# # #             'labels': ['class1', 'class2', 'class3']
# # #         }
# # #     mock.inference = inference
# # #     return mock

# # # @pytest.mark.pipeline
# # # def test_train_pipeline(mock_audio_files, mock_cnn14):
# # #     """Test training pipeline end-to-end"""
# # #     data_dir, classes = mock_audio_files
    
# # #     with patch('backbones.cnn14.load_cnn14_model', return_value=mock_cnn14):
# # #         # Train a head model
# # #         output_dir = data_dir.parent / "models"
# # #         output_dir.mkdir()
        
# # #         head_path = train_head_from_dir(
# # #             audio_dir=str(data_dir / "train"),
# # #             output_dir=str(output_dir),
# # #             backbone="cnn14",
# # #             head_type="rf",
# # #             batch_size=2
# # #         )
        
# # #         # Verify outputs
# # #         assert Path(head_path).exists()
# # #         assert Path(head_path + ".meta.json").exists()

# # # @pytest.mark.pipeline
# # # def test_inference_pipeline(mock_audio_files, mock_cnn14):
# # #     """Test inference pipeline end-to-end"""
# # #     data_dir, classes = mock_audio_files
# # #     test_file = next(data_dir.rglob("*.wav"))
    
# # #     with patch('backbones.cnn14.load_cnn14_model', return_value=mock_cnn14):
# # #         # Create a mock head model
# # #         output_dir = data_dir.parent / "models"
# # #         output_dir.mkdir()
        
# # #         # Train a model first
# # #         head_path = train_head_from_dir(
# # #             audio_dir=str(data_dir / "train"),
# # #             output_dir=str(output_dir),
# # #             backbone="cnn14",
# # #             head_type="rf",
# # #             batch_size=2
# # #         )
        
# # #         # Run inference
# # #         results = run_inference(
# # #             audio_path=str(test_file),
# # #             head_path=head_path,
# # #             backbone="cnn14",
# # #             window_sec=1.0,
# # #             hop_sec=0.5
# # #         )
        
# # #         assert isinstance(results, dict)
# # #         assert "predictions" in results
# # #         assert len(results["predictions"]) > 0

# # # @pytest.mark.pipeline
# # # def test_pipeline_error_handling(mock_audio_files):
# # #     """Test error handling in pipeline"""
# # #     data_dir, classes = mock_audio_files
    
# # #     # Test with missing backbone
# # #     with pytest.raises(ValueError):
# # #         train_head_from_dir(
# # #             audio_dir=str(data_dir / "train"),
# # #             output_dir=str(data_dir.parent / "models"),
# # #             backbone="nonexistent",
# # #             head_type="rf"
# # #         )
    
# # #     # Test with empty directory
# # #     empty_dir = data_dir.parent / "empty"
# # #     empty_dir.mkdir()
# # #     with pytest.raises(ValueError):
# # #         train_head_from_dir(
# # #             audio_dir=str(empty_dir),
# # #             output_dir=str(data_dir.parent / "models"),
# # #             backbone="cnn14",
# # #             head_type="rf"
# # #         )

# # # @pytest.mark.pipeline 
# # # def test_pipeline_with_different_backbones(mock_audio_files):
# # #     """Test pipeline with different backbone models"""
# # #     data_dir, classes = mock_audio_files
    
# # #     # Only test CNN14 for now since that's what we support
# # #     cnn14_mock = Mock()
# # #     cnn14_mock.inference.return_value = {
# # #         'clipwise_output': torch.tensor([0.3, 0.4, 0.3]),
# # #         'embedding': torch.randn(128)
# # #     }
    
# # #     with patch('backbones.cnn14.load_cnn14_model', return_value=cnn14_mock):
# # #         output_dir = data_dir.parent / "models_cnn14"
# # #         output_dir.mkdir()
        
# # #         # Train with CNN14
# # #         head_path = train_head_from_dir(
# # #             audio_dir=str(data_dir / "train"),
# # #             output_dir=str(output_dir),
# # #             backbone="cnn14",
# # #             head_type="rf",
# # #             batch_size=2
# # #         )
        
# # #         # Verify outputs
# # #         assert Path(head_path).exists()
# # #         assert Path(head_path + ".meta.json").exists()