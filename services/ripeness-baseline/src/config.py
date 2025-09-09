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

# ספי ברירת מחדל: ניתן לשנות בהמשך לפי זן/דאטה אמיתי
THRESHOLDS = {
    "overripe_brown_ratio": 0.25,
    "overripe_min_v": 70,       # אם נמוך מזה -> overripe
    "unripe_h_min": 40,
    "unripe_h_max": 90,
    "low_light_v": 60,
    "blurry_lap_var": 80.0,
    "small_mask_cov": 0.20,
    "near_brown_delta": 0.03
}
