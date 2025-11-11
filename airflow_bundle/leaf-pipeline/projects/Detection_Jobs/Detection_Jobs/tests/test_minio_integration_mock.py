# Purpose: Mock-based integration tests for MinIO storage.
# Simulates MinIO object downloads, saves them locally, and verifies images can be loaded successfully.

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Dict, Iterable

import pytest
from PIL import Image

from agri_baseline.src.storage import minio_sync
from agri_baseline.src.storage.minio_client import MinioConfig
from agri_baseline.src.pipeline.utils import load_image


class _FakeObj:
    """Mimics the object returned by client.list_objects()."""

    def __init__(self, object_name: str) -> None:
        self.object_name = object_name


class _FakeResponse:
    """
    Minimal MinIO get_object-like response object.

    Provides:
    - read(amt: int | None = None) -> bytes
    - close() -> None
    - release_conn() -> None

    This mirrors what MinIO/urllib3 responses typically expose, so production code
    that calls release_conn() won't fail under the mock.
    """

    def __init__(self, data: bytes) -> None:
        self._buf = BytesIO(data)

    def read(self, amt: int | None = None) -> bytes:
        return self._buf.read() if amt is None else self._buf.read(amt)

    def close(self) -> None:
        self._buf.close()

    def release_conn(self) -> None:
        # In real clients this releases underlying HTTP resources.
        # No-op here is fine for tests.
        pass


class _FakeMinio:
    """
    Fake MinIO client that supports the subset used by minio_sync:
    - list_objects(bucket, prefix, recursive) -> Iterable[_FakeObj]
    - get_object(bucket, key) -> _FakeResponse
    """

    def __init__(self, payload_by_key: Dict[str, bytes]) -> None:
        self._payload_by_key = payload_by_key

    def list_objects(self, bucket: str, prefix: str, recursive: bool) -> Iterable[_FakeObj]:
        for key in self._payload_by_key:
            if key.startswith(prefix) and not key.endswith("/"):
                yield _FakeObj(key)

    def get_object(self, bucket: str, key: str) -> _FakeResponse:
        data = self._payload_by_key[key]
        return _FakeResponse(data)


@pytest.fixture
def fake_jpeg() -> bytes:
    """Create a tiny deterministic JPEG in-memory."""
    img = Image.new("RGB", (32, 24), (10, 20, 30))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_minio_download_and_load(monkeypatch: pytest.MonkeyPatch,
                                 tmp_path: Path,
                                 fake_jpeg: bytes) -> None:
    """
    Flow under test:
    1) list prefix from MinIO (fake).
    2) download files to local cache dir.
    3) ensure those files exist and can be loaded with load_image.
    """

    # 1) Arrange fake MinIO payload (two images under mission-123/)
    payload = {
        "mission-123/imgA.jpg": fake_jpeg,
        "mission-123/imgB.jpg": fake_jpeg,
    }
    fake_client = _FakeMinio(payload)

    # 2) Monkeypatch build_client to return our fake client
    monkeypatch.setattr(minio_sync, "build_client", lambda cfg: fake_client, raising=True)

    # 3) Prepare config and download target folder
    cfg = MinioConfig(
        endpoint="127.0.0.1:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="leaves",
        secure=False,
    )
    out_dir = tmp_path / "cache"

    # 4) Act: download objects to local dir
    paths = minio_sync.download_prefix_to_dir(cfg, prefix="mission-123", local_dir=out_dir)

    # 5) Assert: files were written and are loadable
    assert len(paths) == 2, f"Expected 2 files, got {len(paths)}"
    for p in paths:
        assert p.exists() and p.is_file(), f"Missing file: {p}"
        img, w, h = load_image(str(p))
        assert img is not None and w > 0 and h > 0, f"Failed to load image {p}"
