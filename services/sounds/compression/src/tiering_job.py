from pathlib import Path
import time
import argparse
import subprocess
import tempfile
from prototype_lib import (
    iter_input_files, build_ffmpeg_cmds, download_raw_to_temp,
    upload_compressed, delete_object, INPUT_EXTS
)
from minio_client import client, BUCKET_NAME

DEFAULT_RAW_MAX_AGE_HOURS = 24
DEFAULT_COMP_MAX_AGE_DAYS = 90
DEFAULT_LONG_TERM_CODEC = "opus"

def get_age_seconds(obj_name: str, mode: str = "mtime") -> float:
    stat = client.stat_object(BUCKET_NAME, obj_name)
    ts = getattr(stat, "last_modified", None)
    if ts is None:
        return 0
    # last_modified is datetime, convert to timestamp
    return time.time() - ts.timestamp()

def is_older_than(obj_name: str, age_seconds: int, mode: str) -> bool:
    return get_age_seconds(obj_name, mode) >= age_seconds

def encode_and_upload(obj_name: str, codec: str) -> str:
    local_file = download_raw_to_temp(obj_name)
    for c, cmd, outp in build_ffmpeg_cmds(local_file, codec=codec):
        rc = subprocess.call(cmd)
        if rc != 0:
            raise RuntimeError(f"Encode failed: {obj_name} -> {codec}")
        target_obj = upload_compressed(outp)
        outp.unlink()
    local_file.unlink()
    return target_obj

def cleanup_compressed(max_age_days: int, dry_run: bool) -> int:
    if max_age_days <= 0:
        return 0
    cutoff_sec = max_age_days * 86400
    deleted = 0
    for obj in client.list_objects(BUCKET_NAME, prefix="compressed/", recursive=True):
        age = get_age_seconds(obj.object_name)
        if age >= cutoff_sec:
            if dry_run:
                print(f"[DRY] would delete compressed: {obj.object_name}")
            else:
                delete_object(obj.object_name)
                deleted += 1
                print(f"[DEL] compressed old: {obj.object_name}")
    return deleted

def main():
    ap = argparse.ArgumentParser(description="Two-tier storage job with MinIO")
    ap.add_argument("--raw-max-age-hours", type=int, default=None)
    ap.add_argument("--raw-max-age-minutes", type=int, default=None)
    ap.add_argument("--age-mode", choices=["mtime", "ctime"], default="mtime")
    ap.add_argument("--codec", choices=["opus", "flac"], default=DEFAULT_LONG_TERM_CODEC)
    ap.add_argument("--delete-raw-after", action="store_true")
    ap.add_argument("--compressed-max-age-days", type=int, default=DEFAULT_COMP_MAX_AGE_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if args.raw_max_age_minutes is not None:
        raw_age_seconds = args.raw_max_age_minutes * 60
    elif args.raw_max_age_hours is not None:
        raw_age_seconds = args.raw_max_age_hours * 3600
    else:
        raw_age_seconds = DEFAULT_RAW_MAX_AGE_HOURS * 3600

    processed, raw_deleted = 0, 0

    for obj_name in iter_input_files():
        if is_older_than(obj_name, raw_age_seconds, args.age_mode):
            if args.dry_run:
                print(f"[DRY] would encode {obj_name} -> {args.codec.upper()}, delete RAW={args.delete_raw_after}")
                processed += 1
                continue

            try:
                target_obj = encode_and_upload(obj_name, args.codec)
                print(f"[OK] {obj_name} -> {target_obj} ({args.codec})")
                processed += 1

                if args.delete_raw_after:
                    delete_object(obj_name)
                    raw_deleted += 1
                    print(f"[DEL] raw: {obj_name}")

            except Exception as e:
                print(f"[FAIL] {obj_name}: {e}")

    comp_deleted = cleanup_compressed(args.compressed_max_age_days, args.dry_run)

    print(f"Done. Processed={processed}, Raw deletions={raw_deleted}, Compressed deletions={comp_deleted}, "
          f"Mode={args.age_mode}, Threshold={raw_age_seconds}s")


if __name__ == "__main__":
    main()