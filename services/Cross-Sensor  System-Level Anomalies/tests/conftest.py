# tests/conftest.py
import os, shutil, random
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

RNG = np.random.default_rng(42)

def make_base_df(n=1000, inject_anoms=False, inject_rate=0.05):

    df = pd.DataFrame({
        "id": [str(i) for i in range(n)],
        "n": RNG.integers(0, 150, size=n),
        "p": RNG.integers(0, 150, size=n),
        "k": RNG.integers(0, 150, size=n),
        "temperature": RNG.normal(25, 5, size=n),
        "humidity": RNG.normal(70, 10, size=n).clip(0, 100),
        "ph": RNG.normal(6.5, 0.8, size=n).clip(3.5, 9.5),
        "rainfall": RNG.normal(200, 60, size=n).clip(0, None),
        "label": RNG.choice(["rice","wheat","maize","grapes","orange","chickpea","papaya"], size=n),
        "soil_moisture": RNG.normal(20, 6, size=n).clip(0, 100),
        "soil_type": RNG.integers(1, 3+1, size=n),
        "sunlight_exposure": RNG.uniform(5, 12, size=n),
        "wind_speed": RNG.uniform(0.2, 20, size=n),
        "co2_concentration": RNG.normal(400, 40, size=n),
        "organic_matter": RNG.normal(6, 2, size=n).clip(0, None),
        "irrigation_frequency": RNG.integers(1, 6+1, size=n),
        "crop_density": RNG.uniform(5, 100, size=n),
        "pest_pressure": RNG.uniform(1, 100, size=n),
        "fertilizer_usage": RNG.uniform(1, 200, size=n),
        "growth_stage": RNG.integers(1, 3+1, size=n),
        "urban_area_proximity": RNG.uniform(0, 50, size=n),
        "water_source_type": RNG.integers(1, 3+1, size=n),
        "frost_risk": RNG.integers(0, 3+1, size=n),
        "water_usage_efficiency": RNG.uniform(1, 100, size=n),
    })

    injected_ids = set()
    if inject_anoms:
        m = max(1, int(inject_rate * n))
        idx = RNG.choice(n, size=m, replace=False)
        injected_ids = set(df.loc[idx, "id"].astype(str))

        df.loc[idx, "temperature"] += RNG.normal(15, 3, size=m)   
        df.loc[idx, "humidity"]    += RNG.normal(25, 5, size=m)  
        df.loc[idx, "rainfall"]    -= RNG.normal(120, 30, size=m) 
        df.loc[idx, "soil_moisture"] += RNG.normal(20, 5, size=m) 
    return df, injected_ids

@pytest.fixture
def synthetic_dataset(tmp_path):
    n = 1000
    df, injected_ids = make_base_df(n=n, inject_anoms=True, inject_rate=0.06)

    workdir = tmp_path
    (workdir/"data").mkdir(parents=True, exist_ok=True)
    csv_path = workdir/"data"/"Crop_recommendationV2.csv"
    df.to_csv(csv_path, index=False)


    return workdir, csv_path, n, injected_ids

@pytest.fixture
def no_anomaly_dataset_tmpdir(tmp_path):
    n = 600
    df, injected_ids = make_base_df(n=n, inject_anoms=False)
    workdir = tmp_path
    (workdir/"data").mkdir(parents=True, exist_ok=True)
    df.to_csv(workdir/"data"/"Crop_recommendationV2.csv", index=False)
    return workdir, n, injected_ids
