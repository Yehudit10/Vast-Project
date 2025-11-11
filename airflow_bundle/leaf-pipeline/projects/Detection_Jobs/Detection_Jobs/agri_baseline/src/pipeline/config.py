from __future__ import annotations

import os
from pathlib import Path

# Try to load env files both from project root and from agri_baseline/.env
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(dotenv_path=Path("agri_baseline/.env"), override=False)
    load_dotenv(override=False)
except Exception:
    pass

# Prefer standard name DATABASE_URL; fallback to DB_URL; finally default to localhost:5432
DB_URL: str = (
    os.getenv("DATABASE_URL")
    or os.getenv("DB_URL")
    or "postgresql+psycopg2://missions_user:pg123@localhost:5432/missions_db"
)

IMAGES_DIR = os.getenv("IMAGES_DIR", "./data/images")
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 64))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", 4))
MIN_BBOX_AREA = int(os.getenv("MIN_BBOX_AREA", 60))
MIN_COMPONENT_AREA = int(os.getenv("MIN_COMPONENT_AREA", 200))
