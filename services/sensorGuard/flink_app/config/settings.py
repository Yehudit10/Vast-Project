import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    # --- API Configuration ---
    DEVICES_API_BASE = os.getenv("DEVICES_API_BASE", "http://host.docker.internal:8001")
    DEVICES_API_TOKEN = os.getenv("DEVICES_API_TOKEN", None)

    # --- Kafka Configuration ---
    KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "kafka:9092")
    IN_TOPIC = os.getenv("IN_TOPIC", "sensors")
    OUT_TOPIC = os.getenv("OUT_TOPIC", "event_logs_sensors")
    KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "flink-device-pipeline")

    # --- Flink runtime paths ---
    PYTHON_EXEC = os.getenv("PYFLINK_PYTHON", "/opt/venv/bin/python")
    RULES_FILE = BASE_DIR / "config" / "rules.yaml"

settings = Settings()
