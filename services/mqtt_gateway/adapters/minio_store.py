# services/mqtt_gateway/adapters/minio_store.py
# Boto3-based ImageStore adapter with lazy imports for unit-test friendliness.

from __future__ import annotations
from typing import Tuple
import io, hashlib, importlib

from services.mqtt_gateway.io import ImageStore


def _sha256_hex(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()


class Boto3ImageStore(ImageStore):
    """
    Uploads bytes to S3-compatible storage (MinIO).
    Lazy-imports boto3/botocore to avoid hard dependency during unit tests.
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        *,
        addressing_style: str = "path",
        multipart_threshold: int = 5 * 1024 * 1024,
        multipart_chunksize: int = 5 * 1024 * 1024,
        max_concurrency: int = 16,
        retries: int = 3,
    ) -> None:
        # Lazy imports (so importing this module won't require boto3 installed)
        boto3 = importlib.import_module("boto3")
        botocore_config = importlib.import_module("botocore.config")
        s3_transfer = importlib.import_module("boto3.s3.transfer")

        BotoConfig = botocore_config.Config
        TransferConfig = s3_transfer.TransferConfig

        self._s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": addressing_style},
                max_pool_connections=max(64, max_concurrency * 2),
                retries={"max_attempts": retries, "mode": "standard"},
            ),
        )
        self._tx = TransferConfig(
            multipart_threshold=multipart_threshold,
            multipart_chunksize=multipart_chunksize,
            max_concurrency=max_concurrency,
            use_threads=True,
        )

    def put_object(self, bucket: str, key: str, data: bytes, content_type: str) -> Tuple[str, int]:
        if not bucket or not key:
            raise ValueError("bucket/key must be non-empty")
        if data is None:
            raise ValueError("data must not be None")
        ctype = content_type or "application/octet-stream"

        sha = _sha256_hex(data)
        size = len(data)
        extra = {"ContentType": ctype, "Metadata": {"checksum-sha256": sha}}

        if size >= self._tx.multipart_threshold:
            bio = io.BytesIO(data)
            self._s3.upload_fileobj(bio, bucket, key, ExtraArgs=extra, Config=self._tx)
        else:
            self._s3.put_object(Bucket=bucket, Key=key, Body=data, **extra)

        return sha, size
