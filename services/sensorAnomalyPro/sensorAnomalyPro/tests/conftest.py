
import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np
import pytest
from datetime import datetime, timedelta

# Ensure project src is importable
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "sensor-anomaly-pro" / "sensor-anomaly-pro"
if SRC.exists():
    sys.path.insert(0, str(SRC))

@pytest.fixture(scope="session")
def mini_csv(tmp_path_factory):
    # Create a tiny, valid sensors CSV for tests and set DATA_PATH to it.
    tmpdir = tmp_path_factory.mktemp("data")
    csv_path = tmpdir / "mini_plant_health.csv"

    # Build 3 days hourly for 2 plants
    start = datetime(2024, 1, 1, 0, 0, 0)
    rows = []
    for plant in ["P1", "P2"]:
        for h in range(0, 24 * 3):
            ts = start + timedelta(hours=h)
            rows.append({
                "Plant_ID": plant,
                "Timestamp": ts.isoformat(),
                "Soil_Moisture": 40 + 10*np.sin(h/6.0) + (np.random.rand()-0.5),
                "Ambient_Temperature": 20 + 5*np.sin(h/12.0) + (np.random.rand()-0.5),
                "Humidity": 60 + 8*np.cos(h/8.0) + (np.random.rand()-0.5),
            })
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)

    os.environ["DATA_PATH"] = str(csv_path)
    return csv_path
