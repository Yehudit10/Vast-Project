# tests/test_app_score.py
import os
from pathlib import Path

import analyze_sensors as az
import sensorAnomalyPro.profiles_runtime as pr
import sensorAnomalyPro.app as appmod

def test_score_function_end_to_end(tmp_path):
    df = az.read_and_clean(Path(os.getenv("DATA_PATH", "/mnt/data/plant_health_data.csv")))

    pr.MODELS_DIR = tmp_path / "reports" / "models"
    pr.MODELS_DIR.mkdir(parents=True, exist_ok=True)

    pr.export_profiles(df)


    row0 = df[df["Plant_ID"].notna()].iloc[0]
    plant = row0["Plant_ID"]
    sensor = "Soil_Moisture" if "Soil_Moisture" in df.columns else "Humidity"

   
    ts = row0["Timestamp"].isoformat()
    value = float(row0[sensor])
    req = appmod.ScoreRequest(plant_id=str(plant), sensor=sensor, ts=ts, value=value) 
    resp = appmod.score(req)

    assert resp.ok is True
    for field in ["is_anomaly", "lower", "upper", "band_std", "flags", "ts", "baseline"]:
        assert getattr(resp, field, None) is not None
