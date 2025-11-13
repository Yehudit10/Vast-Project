import os
from pathlib import Path
import pandas as pd

import analyze_sensors as az

def test_read_and_clean_smoke():
    data_path = Path(os.getenv("DATA_PATH", "/mnt/data/plant_health_data.csv"))
    df = az.read_and_clean(data_path)
    assert not df.empty, "cleaned dataframe should not be empty"
    # required columns
    required = {"Plant_ID", "Timestamp"}
    assert required.issubset(df.columns), f"missing columns: {required - set(df.columns)}"
    # dtypes
    assert pd.api.types.is_datetime64_any_dtype(df["Timestamp"]), "Timestamp must be datetime"
    for col in ["Soil_Moisture", "Ambient_Temperature", "Humidity"]:
        assert col in df.columns, f"missing sensor column {col}"
