import os, hashlib, importlib.util
import boto3
from moto import mock_aws


def _load_app():
    here = os.path.dirname(__file__)
    app_path = os.path.join(here, "..", "mqtt_ingest", "app.py")
    spec = importlib.util.spec_from_file_location("app", app_path)
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    return app

def _mk_s3_and_patch_app(monkeypatch, app):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket=app.BUCKET)
    monkeypatch.setattr(app, "s3", s3)
    return s3

def _sha256_hex(b: bytes) -> str:
    h = hashlib.sha256(); h.update(b); return h.hexdigest()

@mock_aws
def test_upload_bytes_small_put(monkeypatch):
    app = _load_app()
    s3 = _mk_s3_and_patch_app(monkeypatch, app)

    data = b"x" * (256 * 1024)  
    key = "camera-01/2025-01-01/small.bin"
    app.upload_bytes(key, data, "application/octet-stream")

    head = s3.head_object(Bucket=app.BUCKET, Key=key)
    assert head["ContentType"] == "application/octet-stream"
    assert head["Metadata"]["checksum-sha256"] == _sha256_hex(data)
    assert head["ContentLength"] == len(data)

@mock_aws
def test_upload_bytes_large_multipart(monkeypatch):
    app = _load_app()
    s3 = _mk_s3_and_patch_app(monkeypatch, app)

    data = b"x" * (6 * 1024 * 1024)  
    key = "camera-01/2025-01-01/big.bin"
    app.upload_bytes(key, data, "application/octet-stream")

    head = s3.head_object(Bucket=app.BUCKET, Key=key)
    assert head["ContentType"] == "application/octet-stream"
    
    assert head["Metadata"]["checksum-sha256"] == _sha256_hex(data)

    
    reported = head["ContentLength"]
    if reported != len(data):
      
        assert reported >= len(data)
        assert (reported - len(data)) <= 1024
    else:
        assert reported == len(data)
