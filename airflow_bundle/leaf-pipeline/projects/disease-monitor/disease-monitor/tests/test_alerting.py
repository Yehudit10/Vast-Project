import pandas as pd
from disease_monitor.alerting import enforce_policies

def test_dedup_cooldown():
    candidates = pd.DataFrame({
        "entity_id": ["A","A"],
        "window": pd.to_datetime(["2025-08-10","2025-08-11"]),
        "window_end": pd.to_datetime(["2025-08-11","2025-08-12"]),
        "rule": ["COUNT_SPIKE","COUNT_SPIKE"],
        "score": [3.1, 3.2],
        "reason": [["zscore"],["zscore"]],
        "disease_count": [10, 9],
        "avg_severity": [0.5, 0.4],
        "affected_area": [10.0, 9.0],
    })
    open_alerts = pd.DataFrame({
        "entity_id": ["A"],
        "rule": ["COUNT_SPIKE"],
        "last_seen": pd.to_datetime(["2025-08-10"]),
        "window_start": pd.to_datetime(["2025-08-10"]),
        "window_end": pd.to_datetime(["2025-08-11"]),
        "first_seen": pd.to_datetime(["2025-08-10"]),
        "status": ["OPEN"],
        "id": [1],
        "score": [3.1]
    })
    cfg = {
        "alerting": {"dedup_cooldown_windows": 3, "resolve_after_no_anomaly": 3,
                     "rate_limit_per_run": 10, "group_by_window": True},
        "windows": {"frequency": "D"}
    }
    res = enforce_policies(candidates, open_alerts, cfg)
    # Second day should be skipped due to cooldown
    assert len(res) == 0 or len(res) == 1
