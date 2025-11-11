from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
from typing import Iterable

from .minio_client import MinioConfig, build_client


def ensure_bucket(cfg: MinioConfig) -> None:
    """
    Ensure the target bucket exists; create it if it does not.
    """
    client = build_client(cfg)
    if not client.bucket_exists(cfg.bucket):
        client.make_bucket(cfg.bucket)


def download_prefix_to_dir(cfg: MinioConfig, prefix: str, local_dir: Path) -> list[Path]:
    """
    Download all objects under the given `prefix` to the local directory.
    Returns a list of local file paths that were downloaded.
    """
    client = build_client(cfg)
    local_dir.mkdir(parents=True, exist_ok=True)

    downloaded: list[Path] = []
    for obj in client.list_objects(cfg.bucket, prefix=prefix, recursive=True):
        # Skip entries that represent "virtual folders"
        name = obj.object_name
        if name.endswith("/") or not name:
            continue

        # Simplify: save using the file's basename only.
        # If you need to preserve the full hierarchy, use: local_dir.joinpath(name)
        target = local_dir.joinpath(Path(name).name)

        response = client.get_object(cfg.bucket, name)
        try:
            data = response.read()
        finally:
            response.close()
            response.release_conn()

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        downloaded.append(target)

    return downloaded


def upload_dir_to_prefix(cfg: MinioConfig, local_dir: Path, prefix: str) -> list[str]:
    """
    Upload all files from the local directory under the given `prefix`.
    Returns a list of object names that were uploaded.
    """
    client = build_client(cfg)
    ensure_bucket(cfg)

    uploaded: list[str] = []
    for path in local_dir.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(local_dir).as_posix()
        object_name = f"{prefix.rstrip('/')}/{rel}"
        data = path.read_bytes()
        bio = BytesIO(data)

        client.put_object(cfg.bucket, object_name, bio, length=len(data))
        uploaded.append(object_name)

    return uploaded
