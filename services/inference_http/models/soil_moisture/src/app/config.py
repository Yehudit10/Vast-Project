import os
import yaml
from dataclasses import dataclass
from typing import Dict, Any
from dotenv import load_dotenv
load_dotenv()

@dataclass
class Settings:
    kafka_brokers: str = os.getenv("KAFKA_BROKERS", "localhost:9092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "irrigation.control")
    kafka_dlt: str = os.getenv("KAFKA_DLT", "irrigation.control.dlq")
    pg_dsn: str = os.getenv("PG_DSN", "postgresql://postgres:postgres@localhost:5432/soil")
    zones_file: str = os.getenv("ZONES_FILE", "configs/zones.yaml")
    decision_window_sec: int = int(os.getenv("DECISION_WINDOW_SEC", "1"))
    patch_size: int = int(os.getenv("PATCH_SIZE", "256"))
    patch_stride: int = int(os.getenv("PATCH_STRIDE", "256"))

def load_zones(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
