"""
run_batch.py

Purpose:
- Run the disease-detection batch pipeline either from a LOCAL folder of images
  or from a MinIO bucket (objects are first downloaded to a local cache dir,
  then processed exactly like local files).

Usage examples:
1) Local folder (backward-compatible):
   python -m agri_baseline.scripts.run_batch --storage local --images ./data/images

2) MinIO (reads config from ENV and optional CLI flags):
   python -m agri_baseline.scripts.run_batch --storage minio --minio-prefix ""

Environment variables (typical .env):
- STORAGE_BACKEND=minio|local
- MINIO_ENDPOINT=127.0.0.1:9000
- MINIO_ACCESS_KEY=minioadmin
- MINIO_SECRET_KEY=minioadmin
- MINIO_BUCKET=leaves
- MINIO_SECURE=false
- MINIO_PREFIX=mission-123/        (optional)
- MINIO_CACHE_DIR=./data/_minio_cache
"""

import argparse
import os
from pathlib import Path

from agri_baseline.src.pipeline.logging_setup import setup_logging
from agri_baseline.src.pipeline import config
from agri_baseline.src.batch_runner import BatchRunner

# MinIO helpers provided in your project
from agri_baseline.src.storage.minio_client import load_minio_config  # loads config from ENV
from agri_baseline.src.storage.minio_sync import download_prefix_to_dir, ensure_bucket


def run_local(images_dir: Path) -> None:
    """
    LOCAL mode:
    - Run the batch pipeline over a local folder of images.
    - This preserves the original behavior for backward compatibility.
    """
    runner = BatchRunner()
    runner.run_folder(images_dir)


def run_minio(prefix: str, cache_dir: Path) -> None:
    """
    MINIO mode:
    - Pull objects from a MinIO bucket (based on ENV config).
    - Download them to a local cache directory.
    - Run the batch pipeline over the downloaded files.
    """
    cfg = load_minio_config()
    ensure_bucket(cfg)  # Safety: create the bucket if it doesn't exist

    cache_dir.mkdir(parents=True, exist_ok=True)

    # Download objects under 'prefix' into the local cache folder
    downloaded = download_prefix_to_dir(cfg, prefix=prefix, local_dir=cache_dir)
    if not downloaded:
        raise SystemExit(
            f"No objects found in bucket '{cfg.bucket}' with prefix '{prefix}'."
        )

    runner = BatchRunner()
    runner.run_folder(cache_dir)


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments and provide sensible defaults from ENV where applicable.
    """
    ap = argparse.ArgumentParser(description="Run batch pipeline (local/minio).")

    # Backward-compatible local images folder
    ap.add_argument(
        "--images",
        default=config.IMAGES_DIR,
        help="Folder of input images (LOCAL mode)",
    )

    # Storage backend selector
    ap.add_argument(
        "--storage",
        choices=["local", "minio"],
        default=os.getenv("STORAGE_BACKEND", "local").lower(),
        help="Where to read images from (local|minio).",
    )

    # MinIO options (with ENV fallbacks)
    ap.add_argument(
        "--minio-prefix",
        default=os.getenv("MINIO_PREFIX", ""),
        help="Object prefix inside the bucket (e.g. 'mission-123/').",
    )
    ap.add_argument(
        "--minio-cache",
        default=os.getenv("MINIO_CACHE_DIR", "./data/_minio_cache"),
        help="Local temp folder used to download MinIO objects before processing.",
    )

    return ap.parse_args()


def main() -> None:
    """
    Entry point:
    - Logs chosen backend.
    - Dispatches to local/minio flows.
    - Keeps logs concise and informative for CI/ops.
    """
    log = setup_logging()
    args = parse_args()

    log.info(f"Storage backend: {args.storage}")

    if args.storage == "local":
        images_dir = Path(args.images)
        log.info(f"Starting batch over LOCAL folder: {images_dir}")
        run_local(images_dir)
        log.info("Batch done (local).")
    else:
        cache_dir = Path(args.minio_cache)
        log.info(
            "Starting batch over MINIO: "
            f"bucket from ENV, prefix='{args.minio_prefix}', cache='{cache_dir}'"
        )
        run_minio(prefix=args.minio_prefix, cache_dir=cache_dir)
        log.info("Batch done (minio).")


if __name__ == "__main__":
    main()
