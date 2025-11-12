from __future__ import annotations
import logging
from typing import List, Dict, Any, Tuple
import pandas as pd
import numpy as np
from scipy import stats

LOGGER = logging.getLogger(__name__)

def zscore_anomalies(df: pd.DataFrame, threshold: float, min_count: int) -> pd.DataFrame:
    s = df["disease_count"]
    mu = df["disease_count_bl"]
    # Use small epsilon for zero/NaN std to avoid z=0
    sd = df["disease_count_std"]
    eps = 1e-6
    sd = sd.where(sd > 0, other=eps).fillna(eps)

    z = (s - mu) / sd
    cond = (z >= threshold) & (s >= min_count)

    out = df.loc[cond].copy()
    out["score"] = z.loc[cond]
    out["rule"] = "COUNT_SPIKE"
    out["reason"] = "zscore"
    return out

def iqr_anomalies(df: pd.DataFrame, k: float, min_count: int) -> pd.DataFrame:
    q1 = df["disease_count_q1"]
    q3 = df["disease_count_q3"]
    iqr = (q3 - q1).replace(0, np.nan)
    upper = q3 + k * iqr
    cond = (df["disease_count"] > upper.fillna(float("inf"))) & (df["disease_count"] >= min_count)
    out = df.loc[cond].copy()
    out["score"] = (df["disease_count"] - upper).loc[cond].fillna(0.0)
    out["rule"] = "COUNT_SPIKE"
    out["reason"] = "iqr"
    return out

def slope_worsening(df: pd.DataFrame, metric: str, lookback: int,
                    slope_min: float, min_periods: int) -> pd.DataFrame:
    # Per entity rolling slope (OLS)
    rows = []
    for entity, g in df.groupby("entity_id"):
        g = g.sort_values("window")
        y = g[metric].rolling(lookback, min_periods=min_periods).apply(_rolling_slope, raw=False)
        cond = y >= slope_min
        sel = g.loc[cond].copy()
        if sel.empty:
            continue
        sel["score"] = y.loc[cond]
        sel["rule"] = "WORSENING_TREND"
        sel["reason"] = f"slope_{metric}"
        rows.append(sel)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=df.columns.tolist() + ["score","rule","reason"])

def _rolling_slope(s: pd.Series) -> float:
    x = np.arange(len(s))
    res = stats.linregress(x, s.values)
    return float(res.slope)

def ewma_worsening(df: pd.DataFrame, metric: str, span: int, threshold: float, min_periods: int) -> pd.DataFrame:
    rows = []
    for entity, g in df.groupby("entity_id"):
        g = g.sort_values("window").copy()
        ew = g[metric].ewm(span=span, adjust=False).mean()
        cond = (ew >= threshold) & (g[metric].rolling(span, min_periods=min_periods).count() >= min_periods)
        sel = g.loc[cond].copy()
        if sel.empty:
            continue
        sel["score"] = ew.loc[cond]
        sel["rule"] = "WORSENING_TREND"
        sel["reason"] = f"ewma_{metric}"
        rows.append(sel)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=df.columns.tolist() + ["score","rule","reason"])

def apply_rules(df: pd.DataFrame, cfg: Dict[str, Any]) -> pd.DataFrame:
    results = []

    # Count anomaly
    rc = cfg["rules"]["count_anomaly"]
    if rc["enabled"]:
        if rc["method"] == "zscore":
            results.append(zscore_anomalies(df, rc["z_threshold"], rc["min_count"]))
        elif rc["method"] == "iqr":
            results.append(iqr_anomalies(df, rc["iqr_k"], rc["min_count"]))
        else:
            # Placeholder: CUSUM can be added similarly
            results.append(zscore_anomalies(df, rc["z_threshold"], rc["min_count"]))

    # Worsening trend on severity and area
    rw = cfg["rules"]["worsening"]
    if rw["enabled"]:
        if rw["method"] == "slope":
            for m in ["avg_severity", "affected_area"]:
                results.append(slope_worsening(df, m, rw["slope_lookback"], rw["slope_min"], rw["min_periods"]))
        else:
            for m in ["avg_severity", "affected_area"]:
                results.append(ewma_worsening(df, m, rw["ewma_span"], rw["ewma_threshold"], rw["min_periods"]))

    if not results:
        return pd.DataFrame()
    out = pd.concat([r for r in results if r is not None and not r.empty], ignore_index=True) \
             if any((r is not None and not r.empty) for r in results) else pd.DataFrame()
    # Prepare common fields
    if not out.empty:
        out = out[["entity_id", "window", "window_end", "rule", "score", "reason",
                   "disease_count", "avg_severity", "affected_area"]].copy()
    return out
