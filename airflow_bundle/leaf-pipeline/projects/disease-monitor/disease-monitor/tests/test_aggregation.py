import pandas as pd
from disease_monitor.io import aggregate

def test_aggregate_basic():
    det = pd.DataFrame({
        "timestamp": pd.to_datetime(["2025-08-01", "2025-08-01", "2025-08-02"]).tz_localize("UTC"),
        "entity_id": ["A","A","A"],
        "disease_type": ["x","x","x"],
        "severity": [0.2, 0.4, 0.3],
        "affected_area": [1,2,3],
    })
    out = aggregate(det, "D")
    assert len(out) == 2
    d1 = out[out["window"] == pd.to_datetime("2025-08-01")]
    assert int(d1["disease_count"].iloc[0]) == 2
    assert abs(float(d1["avg_severity"].iloc[0]) - 0.3) < 1e-9
    assert int(d1["affected_area"].iloc[0]) == 3
