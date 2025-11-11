import pandas as pd
from disease_monitor.baseline import compute_baseline
from disease_monitor.rules import apply_rules

def test_zscore_spike_detected():
    # mostly low counts, then spike
    det = []
    for d in range(10):
        det.append({"window": pd.to_datetime(f"2025-08-{d+1:02d}"),
                    "entity_id": "E1",
                    "disease_count": 1 if d < 8 else (10 if d==8 else 1),
                    "avg_severity": 0.2, "affected_area": 2.0})
    df = pd.DataFrame(det)
    df["window_end"] = df["window"] + pd.Timedelta(days=1)
    bl = compute_baseline(df.rename(columns={"window":"window"}), "median", 7, 3, None)
    cfg = {
        "rules": {"count_anomaly": {"enabled": True, "method": "zscore", "z_threshold": 2.5, "min_count": 3},
                  "worsening": {"enabled": False}},
    }
    out = apply_rules(bl, cfg)
    assert not out.empty
    assert "COUNT_SPIKE" in out["rule"].unique()
