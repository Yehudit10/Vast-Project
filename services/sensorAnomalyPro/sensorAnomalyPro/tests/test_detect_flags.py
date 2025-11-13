# tests/test_detect_flags.py
import os
from pathlib import Path
import numpy as np

import analyze_sensors as az

def test_detect_flags_spike_is_caught():
    data_path = Path(os.getenv("DATA_PATH", "/mnt/data/plant_health_data.csv"))
    df = az.read_and_clean(data_path)

    col = "Soil_Moisture" if "Soil_Moisture" in df.columns else "Humidity"

   
    plant_val = df["Plant_ID"].dropna().unique()[0]
    d = df[df["Plant_ID"] == plant_val].copy()
    assert not d.empty, "no rows for selected plant"

    mid = len(d) // 2
    base = float(d.iloc[mid][col])
    d.iloc[mid, d.columns.get_loc(col)] = base + 50.0 

  
    db = az.baseline_daily(d, col)
    out = az.detect_flags(db, col)

    expected = {"flag_band", "flag_spike", "flag_break", "is_anomaly"}
    assert expected.issubset(set(out.columns)), f"missing columns: {expected - set(out.columns)}"

  
    flag_df = out[["flag_band", "flag_spike", "flag_break", "is_anomaly"]].fillna(False)
    assert flag_df.to_numpy().any(), "expected at least one flagged point for the injected spike"

  
    assert flag_df["flag_spike"].any() or flag_df["is_anomaly"].any(), "expected spike detection"
