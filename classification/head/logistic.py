from __future__ import annotations
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

def build_head_pipeline(seed: int) -> Pipeline:
    """
    Balanced multinomial Logistic Regression over embeddings.
    """
    return Pipeline([
        ("scaler", StandardScaler()),
        ("clf", LogisticRegression(
            max_iter=2000,
            class_weight="balanced",
            multi_class="multinomial",
            solver="saga",
            random_state=int(seed),
            n_jobs=-1,
        )),
    ])
