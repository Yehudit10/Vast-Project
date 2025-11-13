import pandas as pd
import random
from datetime import datetime, timezone

def generate_sensor_data():
    df = pd.read_csv("Crop_recommendationV2.csv")
    dfs = pd.read_csv("place.csv")

    row = df.sample(1).iloc[0]
    place_row = dfs.sample(1).iloc[0]

    sensor_id = int(place_row["id"])
    plant_id = int(place_row["plant_id"])
    sensor = str(place_row["sensor_type"])
    value = float(place_row["value"])
    lat = float(place_row["lat"])
    lon = float(place_row["lon"])

    data = {
        "sid": f"sensor-{sensor_id}",
        "id": sensor_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "msg_type": "telemetry",
        "value": value,
        "plant_id": plant_id,
        "sensor_name": sensor,
        "n": float(row["N"]),
        "p": float(row["P"]),
        "k": float(row["K"]),
        "temperature": float(row["temperature"]),
        "humidity": float(row["humidity"]),
        "ph": float(row["ph"]),
        "rainfall": float(row["rainfall"]),
        "label": str(row["label"]),
        "soil_moisture": float(row["soil_moisture"]),
        "soil_type": int(row["soil_type"]),
        "sunlight_exposure": float(row["sunlight_exposure"]),
        "wind_speed": float(row["wind_speed"]),
        "co2_concentration": float(row["co2_concentration"]),
        "organic_matter": float(row["organic_matter"]),
        "irrigation_frequency": float(row["irrigation_frequency"]),
        "crop_density": float(row["crop_density"]),
        "pest_pressure": float(row["pest_pressure"]),
        "fertilizer_usage": float(row["fertilizer_usage"]),
        "growth_stage": int(row["growth_stage"]),
        "urban_area_proximity": float(row["urban_area_proximity"]),
        "water_source_type": int(row["water_source_type"]),
        "frost_risk": float(row["frost_risk"]),
        "water_usage_efficiency": float(row["water_usage_efficiency"]),
        "lat": lat,
        "lon": lon,
        "sensor_type": sensor
    }

    return data
