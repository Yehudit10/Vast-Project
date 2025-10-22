from __future__ import annotations
from sklearn.pipeline import Pipeline

from .logistic import build_head_pipeline as _build_lr
from .svm import build_head_pipeline as _build_svm
from .rf import build_head_pipeline as _build_rf

def build_head_pipeline(head_type: str = "rf", seed: int = 42) -> Pipeline:
    """
    Factory to build a classification head with predict_proba support.
    Valid head_type: 'logreg' | 'svm' | 'rf'
    """
    t = (head_type or "rf").strip().lower()
    if t in ("logreg", "lr", "logistic"):
        return _build_lr(seed)
    if t in ("svm", "svc", "linear_svm"):
        return _build_svm(seed)
    if t in ("rf", "random_forest", "randomforest"):
        return _build_rf(seed)
    raise ValueError(f"Unsupported head_type: {head_type}")
