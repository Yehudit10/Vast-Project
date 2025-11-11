from __future__ import annotations
import pandas as pd
import numpy as np

def compute_baseline(agg: pd.DataFrame, method: str, lookback: int,
                     min_history: int, seasonality: int | None) -> pd.DataFrame:
    """
    Returns agg with baseline columns for disease_count, avg_severity, affected_area:
    *_bl, *_std (or IQR helpers).
    """
    df = agg.sort_values(["entity_id", "window"]).copy()
    keys = ["entity_id"]
    metrics = ["disease_count", "avg_severity", "affected_area"]

    # Optionally seasonal lag indexing
    if seasonality and seasonality > 1:
        df["season_index"] = df.groupby(keys)["window"].rank(method="first").astype(int) % seasonality
        groupers = keys + ["season_index"]
    else:
        groupers = keys

    for m in metrics:
        if method == "mean":
            bl = df.groupby(groupers)[m].transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_history).mean())
            sd = df.groupby(groupers)[m].transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_history).std(ddof=0))
        else:
            bl = df.groupby(groupers)[m].transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_history).median())
            sd = df.groupby(groupers)[m].transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_history).std(ddof=0))
        df[f"{m}_bl"] = bl.fillna(0.0)
        df[f"{m}_std"] = sd.fillna(0.0)

        # IQR helpers
        q1 = df.groupby(groupers)[m].transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_history).quantile(0.25))
        q3 = df.groupby(groupers)[m].transform(lambda s: s.shift(1).rolling(lookback, min_periods=min_history).quantile(0.75))
        df[f"{m}_q1"] = q1.fillna(0.0)
        df[f"{m}_q3"] = q3.fillna(0.0)

    return df
