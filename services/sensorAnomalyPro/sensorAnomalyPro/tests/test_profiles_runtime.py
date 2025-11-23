# tests/test_profiles_runtime.py
import os
from pathlib import Path

import analyze_sensors as az
import sensorAnomalyPro.profiles_runtime as pr

def test_export_and_load_profiles(tmp_path):
    df = az.read_and_clean(Path(os.getenv("DATA_PATH", "/mnt/data/plant_health_data.csv")))
    pr.MODELS_DIR = tmp_path / "reports" / "models"
    pr.MODELS_DIR.mkdir(parents=True, exist_ok=True)  # לוודא שהתיקייה קיימת
    pr.export_profiles(df)

    plant = df["Plant_ID"].dropna().iloc[0]
    sensor = "Soil_Moisture" if "Soil_Moisture" in df.columns else "Humidity"
    prof = pr.load_profiles(plant, sensor)
    assert prof is not None
