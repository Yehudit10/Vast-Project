# tests/test_large_and_mime.py
import os
import hashlib
import importlib.util
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "mqtt_ingest" / "app.py"

def _load_app():
    spec = importlib.util.spec_from_file_location("app", str(APP_PATH))
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app

def _mk_s3_and_patch(monkeypatch, app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=app.BUCKET)
    monkeypatch.setattr(app, "s3", s3)
    return s3

def _sha256_hex(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

RUN_STRESS = os.getenv("RUN_STRESS") == "1"

@pytest.mark.skipif(not RUN_STRESS, reason="set RUN_STRESS=1 to enable heavy test")
@mock_aws
def test_very_large_upload_multipart(monkeypatch):
    app = _load_app()
    s3 = _mk_s3_and_patch(monkeypatch, app)


    size_mib = int(os.getenv("STRESS_SIZE_MIB", "64"))
    data = (b"x" * (1024 * 1024)) * size_mib   
    key = "camera-01/2025-01-01/huge.bin"

    app.upload_bytes(key, data, "application/octet-stream")

    head = s3.head_object(Bucket=app.BUCKET, Key=key)

    assert head["Metadata"]["checksum-sha256"] == _sha256_hex(data)


    reported = head["ContentLength"]
    if reported != len(data):
        assert reported >= len(data)
        assert (reported - len(data)) <= 2048  
    else:
        assert reported == len(data)


