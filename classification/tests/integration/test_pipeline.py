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
    run_classify_main_with_args(args)
