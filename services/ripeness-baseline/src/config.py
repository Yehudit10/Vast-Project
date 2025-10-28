import os
from dotenv import load_dotenv
load_dotenv()

PG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": int(os.getenv("PGPORT", "5432")),
    "db": os.getenv("PGDATABASE", "agcloud"),
    "user": os.getenv("PGUSER", "postgres"),
    "password": os.getenv("PGPASSWORD", "postgres"),
}

SAMPLES_DIR = os.getenv("SAMPLES_DIR", "./samples")
FRUIT_TYPE  = os.getenv("FRUIT_TYPE", "apple")

THRESHOLDS = {
    "overripe_brown_ratio": 0.10,
    "overripe_min_v": 60,       
    "unripe_h_min": 30,
    "unripe_h_max": 95,
    "low_light_v": 60,
    "blurry_lap_var": 80.0,
    "small_mask_cov": 0.20,
    "near_brown_delta": 0.03,
    "green_leaf_ratio_thr": float(os.getenv("GREEN_LEAF_FLAG_THR", "0.10"))
}

LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "7"))
READ_FROM_LOGS = os.getenv("READ_FROM_LOGS", "0") in ("1", "true", "True")
