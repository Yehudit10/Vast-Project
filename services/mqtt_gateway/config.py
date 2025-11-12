# services/mqtt_gateway/config.py
# Purpose: centralize and validate service configuration (12-factor style).

from __future__ import annotations
from pydantic import BaseModel, Field, AnyUrl, ValidationError
import os

class GatewayConfig(BaseModel):
    # Storage
    minio_endpoint: str = Field(default="http://minio:9000")
    minio_access_key: str = Field(default="minioadmin", min_length=1)
    minio_secret_key: str = Field(default="minioadmin", min_length=1)
    minio_bucket: str = Field(default="rover-images", min_length=1)

    # Kafka
    kafka_bootstrap: str = Field(default="kafka:9092", min_length=1)
    kafka_topic: str = Field(default="rover.images.meta.v1", min_length=1)

    # MQTT
    mqtt_host: str = Field(default="mosquitto")
    mqtt_port: int = Field(default=1883, ge=1)
    mqtt_topic: str = Field(default="MQTT/imagery/#")
    mqtt_client_id: str = Field(default="mqtt-gateway")

    # Server/metrics
    metrics_port: int = Field(default=9110, ge=1024, le=65535)

def load_config() -> GatewayConfig:
    env = os.getenv
    try:
        return GatewayConfig(
            minio_endpoint=env("MINIO_ENDPOINT", "http://minio:9000"),
            minio_access_key=env("MINIO_ACCESS_KEY", "minioadmin"),
            minio_secret_key=env("MINIO_SECRET_KEY", "minioadmin"),
            minio_bucket=env("MINIO_BUCKET", "rover-images"),
            kafka_bootstrap=env("KAFKA_BOOTSTRAP", "kafka:9092"),
            kafka_topic=env("KAFKA_TOPIC", "rover.images.meta.v1"),
            mqtt_host=env("MQTT_HOST", "mosquitto"),
            mqtt_port=int(env("MQTT_PORT", "1883")),
            mqtt_topic=env("MQTT_TOPIC", "MQTT/imagery/#"),
            mqtt_client_id=env("MQTT_CLIENT_ID", "mqtt-gateway"),
            metrics_port=int(env("METRICS_PORT", "9110")),
        )
    except ValidationError as ve:
        raise SystemExit(f"[config] invalid env: {ve}") from ve
