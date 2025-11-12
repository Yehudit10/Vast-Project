from __future__ import annotations

import os
from dataclasses import dataclass
from minio import Minio


@dataclass(frozen=True)
class MinioConfig:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    secure: bool


def load_minio_config() -> MinioConfig:
    endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY", "")
    secret_key = os.getenv("MINIO_SECRET_KEY", "")
    bucket = os.getenv("MINIO_BUCKET", "my-bucket")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

    if not access_key or not secret_key:
        raise ValueError("Missing MINIO_ACCESS_KEY / MINIO_SECRET_KEY.")
    return MinioConfig(endpoint, access_key, secret_key, bucket, secure)


def build_client(cfg: MinioConfig) -> Minio:
    return Minio(
        endpoint=cfg.endpoint,
        access_key=cfg.access_key,
        secret_key=cfg.secret_key,
        secure=cfg.secure,
    )
