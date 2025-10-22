import pytest
from pathlib import Path
import numpy as np
import pandas as pd
from scripts import eval_from_db
import json
import os

def test_infer_true_label_from_path():
    """Test label inference from file paths"""
    valid_labels = ["birds", "vehicle", "fire"]
    
    # Test valid paths
    assert eval_from_db.infer_true_label_from_path("/data/birds/chirp.wav", valid_labels) == "birds"
    assert eval_from_db.infer_true_label_from_path("C:\\Data\\Vehicle\\car.wav", valid_labels) == "vehicle"
    assert eval_from_db.infer_true_label_from_path("/tmp/Fire/sample_1.wav", valid_labels) == "fire"
    
    # Test case insensitive
    assert eval_from_db.infer_true_label_from_path("/data/BIRDS/test.wav", valid_labels) == "birds"
    
    # Test invalid paths
    assert eval_from_db.infer_true_label_from_path("/data/unknown/test.wav", valid_labels) is None
    assert eval_from_db.infer_true_label_from_path("", valid_labels) is None

def test_parse_labels_arg():
    """Test labels argument parsing"""
    # Test default labels
    assert eval_from_db.parse_labels_arg(None) == eval_from_db.DEFAULT_LABELS
    assert eval_from_db.parse_labels_arg("") == eval_from_db.DEFAULT_LABELS
    
    # Test custom labels
    custom = "birds,vehicle,fire"
    expected = ["birds", "vehicle", "fire"]
    assert eval_from_db.parse_labels_arg(custom) == expected
    
    # Test whitespace handling
    messy = " birds , vehicle,  fire  "
    assert eval_from_db.parse_labels_arg(messy) == expected

def test_extract_probs_map():
    """Test probability extraction from JSON"""
    # Test valid JSON string
    json_str = '{"birds": 0.8, "vehicle": 0.2}'
    result = eval_from_db.extract_probs_map(json_str)
    assert result == {"birds": 0.8, "vehicle": 0.2}
    
    # Test dict input
    dict_input = {"birds": 0.8, "vehicle": 0.2}
    assert eval_from_db.extract_probs_map(dict_input) == dict_input
    
    # Test invalid inputs
    assert eval_from_db.extract_probs_map(None) == {}
    assert eval_from_db.extract_probs_map("invalid json") == {}
    assert eval_from_db.extract_probs_map([]) == {}

def test_probs_to_pred():
    """Test prediction extraction from probability map"""
    labels = ["birds", "vehicle", "fire"]
    
    # Test normal case
    probs = {"birds": 0.8, "vehicle": 0.1, "fire": 0.1}
    label, prob = eval_from_db.probs_to_pred(probs, labels)
    assert label == "birds"
    assert prob == 0.8
    
    # Test missing labels
    probs = {"unknown": 1.0}
    label, prob = eval_from_db.probs_to_pred(probs, labels)
    assert label is None
    assert prob is None
    
    # Test empty probs
    label, prob = eval_from_db.probs_to_pred({}, labels)
    assert label is None
    assert prob is None

def test_evaluate_one_run():
    """Test evaluation of a single run"""
    # Create test DataFrame
    df_run = pd.DataFrame({
        "file_path": [
            "/data/birds/test1.wav",
            "/data/vehicle/test2.wav",
            "/data/fire/test3.wav"
        ],
        "head_probs_json": [
            json.dumps({"birds": 0.8, "vehicle": 0.1, "fire": 0.1}),
            json.dumps({"birds": 0.1, "vehicle": 0.7, "fire": 0.2}),
            json.dumps({"birds": 0.2, "vehicle": 0.2, "fire": 0.6})
        ],
        "head_pred_label": ["birds", "vehicle", "fire"],
        "head_pred_prob": [0.8, 0.7, 0.6],
        "head_is_another": [False, False, False]
    })
    
    labels = ["birds", "vehicle", "fire"]
    
    df_eval, summary, cm = eval_from_db.evaluate_one_run(df_run, labels, ignore_another=True)
    
    # Check results
    assert len(df_eval) == 3
    assert summary["accuracy"] == 1.0  # All predictions correct
    assert summary["support"] == 3
    assert summary["coverage_final"] == 1.0
    assert np.all(cm.diagonal() == 1)  # One correct prediction per class

def test_main_with_mocks(monkeypatch, tmp_path):
    """Test main function with mocked database"""
    out_dir = tmp_path / "eval_reports"
    
    # Mock command line arguments
    test_args = [
        "eval_from_db.py",
        "--db-url", "postgresql://fake_url",
        "--out-dir", str(out_dir),
        "--last", "1"
    ]
    monkeypatch.setattr("sys.argv", test_args)
    
    # Mock database connection and query results
    class MockCursor:
        def __enter__(self):
            return self
            
        def __exit__(self, *args):
            pass
            
        def execute(self, *args):
            pass
            
        @property
        def description(self):
            return [
                ("run_id",),
                ("model_name",),
                ("file_path",),
                ("head_probs_json",),
                ("head_pred_label",),
                ("head_pred_prob",),
                ("head_is_another",),
                ("window_sec",),
                ("hop_sec",),
                ("pad_last",),
                ("agg",),
                ("notes",),
            ]
            
        def fetchall(self):
            return [
                ("run1", "cnn14", "/data/birds/test.wav",
                 json.dumps({"birds": 0.8, "vehicle": 0.2}),
                 "birds", 0.8, False, 1.0, 0.5, False, "mean", "")
            ]
    
    class MockConnection:
        def cursor(self):
            return MockCursor()
            
        def commit(self):
            pass
            
        def close(self):
            pass
    
    def mock_connect(*args, **kwargs):
        return MockConnection()
    
    monkeypatch.setattr("psycopg2.connect", mock_connect)
    
    # Run main function
    eval_from_db.main()
    
    # Verify outputs
    assert out_dir.exists()
    assert (out_dir / "runs_summary.csv").exists()
    assert (out_dir / "per_file_run1.csv").exists()
    assert (out_dir / "confusion_run1.csv").exists()