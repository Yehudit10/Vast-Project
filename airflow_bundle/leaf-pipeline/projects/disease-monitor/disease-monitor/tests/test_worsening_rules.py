import pandas as pd
from disease_monitor.baseline import compute_baseline
from disease_monitor.rules import apply_rules

def test_worsening_slope_on_severity():
    rows = []
    for i in range(10):
        rows.append({
            "window": pd.to_datetime(f"2025-08-{i+1:02d}"),
            "entity_id": "E1",
            "disease_count": 1,
            "avg_severity": 0.1 + 0.03*i,
            "affected_area": 2 + i
        })
    df = pd.DataFrame(rows)
    df["window_end"] = df["window"] + pd.Timedelta(days=1)
    bl = compute_baseline(df, "median", 7, 3, None)
    cfg = {"rules":
           {"count_anomaly": {"enabled": False},
            "worsening": {"enabled": True, "method": "slope",
                          "slope_lookback": 7, "slope_min": 0.02, "min_periods": 5}}}
    out = apply_rules(bl, cfg)
    assert not out.empty
    assert "WORSENING_TREND" in out["rule"].unique()
