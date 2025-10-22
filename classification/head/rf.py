from __future__ import annotations
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier

def build_head_pipeline(seed: int) -> Pipeline:
    """
    RandomForest with class_weight; no scaling needed (tree-based).
    'scaler' is kept as passthrough for a uniform interface.
    """
    rf = RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced_subsample",
        random_state=int(seed),
        n_jobs=-1,
    )
    return Pipeline([
        ("scaler", "passthrough"),
        ("clf", rf),
    ])
