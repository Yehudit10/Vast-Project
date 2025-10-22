from __future__ import annotations
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC
from sklearn.calibration import CalibratedClassifierCV

def build_head_pipeline(seed: int) -> Pipeline:
    """
    LinearSVC + probability calibration to expose predict_proba.
    Works well for high-dimensional embeddings.
    """
    base = LinearSVC(
        C=1.0,
        class_weight="balanced",
        random_state=int(seed),
    )
    # In recent scikit-learn versions use 'estimator' (not 'base_estimator')
    clf = CalibratedClassifierCV(
        estimator=base,
        method="sigmoid",
        cv=5,  # if you hit class-count issues, reduce to 3
    )
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", clf),
    ])
