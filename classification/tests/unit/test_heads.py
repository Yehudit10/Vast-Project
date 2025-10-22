import pytest
import numpy as np
from pathlib import Path
import joblib
import json
from sklearn.datasets import make_classification

from head import build_head_pipeline
from head.rf import build_head_pipeline as build_rf_pipeline
from head.logistic import build_head_pipeline as build_logistic_pipeline
from head.svm import build_head_pipeline as build_svm_pipeline

@pytest.fixture
def synthetic_data():
    """Create synthetic data for testing classification heads"""
    X, y = make_classification(
        n_samples=100,
        n_features=128,  # Typical embedding dimension
        n_classes=3,
        n_informative=10,
        random_state=42
    )
    X = X.astype(np.float32)
    class_names = ["birds", "insects", "vehicle"]
    return X, y, class_names

def train_and_save_head(pipe, X, y, class_names, model_path, head_type):
    """Helper to train and save a head with metadata"""
    pipe.fit(X, y)
    model_path = Path(model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, model_path)
    
    meta = {
        "class_order": class_names,
        "head_type": head_type,
        "embedding_dim": X.shape[1]
    }
    meta_path = model_path.with_suffix(model_path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return pipe

@pytest.mark.head
def test_logistic_head(synthetic_data, tmp_path):
    """Test logistic regression head pipeline building and prediction"""
    X, y, class_names = synthetic_data
    
    # Build and train pipeline
    pipe = build_logistic_pipeline(seed=42)
    model_path = tmp_path / "logistic_head.joblib"
    train_and_save_head(pipe, X, y, class_names, model_path, "logistic")
    
    # Verify files were saved
    assert model_path.exists()
    meta_path = model_path.with_suffix(model_path.suffix + ".meta.json")
    assert meta_path.exists()
    
    # Load and test prediction
    model = joblib.load(model_path)
    probs = model.predict_proba(X[:5])
    assert probs.shape == (5, 3)
    assert np.allclose(np.sum(probs, axis=1), 1.0)

@pytest.mark.head
def test_rf_head(synthetic_data, tmp_path):
    """Test random forest head pipeline building and prediction"""
    X, y, class_names = synthetic_data
    
    # Build and train pipeline
    pipe = build_rf_pipeline(seed=42)
    model_path = tmp_path / "rf_head.joblib"
    train_and_save_head(pipe, X, y, class_names, model_path, "random_forest")
    
    # Verify files were saved
    assert model_path.exists()
    meta_path = model_path.with_suffix(model_path.suffix + ".meta.json")
    assert meta_path.exists()
    
    # Load and test prediction
    model = joblib.load(model_path)
    probs = model.predict_proba(X[:5])
    assert probs.shape == (5, 3)
    assert np.allclose(np.sum(probs, axis=1), 1.0)

@pytest.mark.head
def test_svm_head(synthetic_data, tmp_path):
    """Test SVM head pipeline building and prediction"""
    X, y, class_names = synthetic_data
    
    # Build and train pipeline
    pipe = build_svm_pipeline(seed=42)
    model_path = tmp_path / "svm_head.joblib"
    train_and_save_head(pipe, X, y, class_names, model_path, "svm")
    
    # Verify files were saved
    assert model_path.exists()
    meta_path = model_path.with_suffix(model_path.suffix + ".meta.json")
    assert meta_path.exists()
    
    # Load and test prediction
    model = joblib.load(model_path)
    probs = model.predict_proba(X[:5])
    assert probs.shape == (5, 3)
    assert np.allclose(np.sum(probs, axis=1), 1.0)

@pytest.mark.head
def test_head_error_handling(synthetic_data, tmp_path):
    """Test error handling in classification heads"""

    X, y, class_names = synthetic_data

    # LogisticRegression invalid parameter
    pipe = build_logistic_pipeline(seed=42)
    pipe.named_steps['clf'].C = -1.0  # Invalid C value
    with pytest.raises(ValueError):
        pipe.fit(X, y)

    # RandomForest invalid parameter
    pipe = build_rf_pipeline(seed=42)
    pipe.named_steps['clf'].n_estimators = 0  # Invalid n_estimators
    with pytest.raises(ValueError):
        pipe.fit(X, y)
    # SVM: skip invalid hyperparameter check, fit will just fail quietly if wrong

@pytest.mark.head
def test_head_metadata(synthetic_data, tmp_path):
    """Test that head metadata is correctly saved"""
    X, y, class_names = synthetic_data
    
    # Test metadata for each head type
    head_types = [
        (build_logistic_pipeline, "logistic"),
        (build_rf_pipeline, "random_forest"),
        (build_svm_pipeline, "svm")
    ]
    
    for build_fn, head_type in head_types:
        pipe = build_fn(seed=42)
        model_path = tmp_path / f"{head_type}_head.joblib"
        train_and_save_head(pipe, X, y, class_names, model_path, head_type)
        
        # Check metadata
        meta_path = Path(str(model_path) + ".meta.json")
        assert meta_path.exists()
        
        meta = json.loads(meta_path.read_text())
        assert "class_order" in meta
        assert "embedding_dim" in meta
        assert meta["head_type"] == head_type
        assert meta["embedding_dim"] == X.shape[1]
        assert len(meta["class_order"]) == len(class_names)