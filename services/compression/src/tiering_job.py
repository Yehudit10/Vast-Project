from pathlib import Path
import time
import argparse
import subprocess
from prototype_lib import (
    iter_audio_files, 
    build_ffmpeg_cmds, 
    download_raw_to_temp,
    replace_with_compressed,
    delete_object,
    get_file_age_seconds,
    is_older_than
)
from minio_client import client, BUCKET_NAME

DEFAULT_RAW_MAX_AGE_DAYS = 30
DEFAULT_COMP_MAX_AGE_DAYS = 90
DEFAULT_LONG_TERM_CODEC = "opus"

def encode_and_replace(obj_name: str, codec: str) -> str:
    """
    Download audio file, encode it, and replace the original in MinIO.
    
    Returns:
        The new object name (with compressed extension)
    """
    # Skip already compressed files
    if obj_name.lower().endswith((".flac", ".opus")):
        print(f"[SKIP] {obj_name} - Already compressed, skipping.")
        return obj_name
    
    # Download original
    local_file = download_raw_to_temp(obj_name)
    
    # Build encode commands
    encode_cmds = build_ffmpeg_cmds(local_file, codec=codec)
    
    if not encode_cmds:
        local_file.unlink()
        raise RuntimeError(f"No encode commands generated for {obj_name}")
    
    # Take the first codec result
    codec_name, cmd, output_path = encode_cmds[0]
    
    # Run encoding
    print(f"[ENC] Encoding {obj_name} -> {codec_name.upper()}...")
    rc = subprocess.call(cmd)
    
    if rc != 0:
        local_file.unlink()
        output_path.unlink(missing_ok=True)
        raise RuntimeError(f"Encode failed: {obj_name} -> {codec}")
    
    # Replace in MinIO (same path, different extension)
    new_obj_name = replace_with_compressed(obj_name, output_path)
    
    # Cleanup local files
    output_path.unlink()
    local_file.unlink()
    
    return new_obj_name

def cleanup_compressed(max_age_days: int, dry_run: bool) -> int:
    """
    Delete very old compressed files that exceeded retention period.
    Uses MinIO last_modified timestamp (when file was uploaded/compressed).
    """
    if max_age_days <= 0:
        print("[INFO] Compressed cleanup disabled (max_age_days <= 0)")
        return 0
    
    from datetime import datetime, timezone
    cutoff_sec = max_age_days * 86400
    deleted = 0
    
    print(f"[CLEANUP] Checking for compressed files older than {max_age_days} days...")
    
    for obj in client.list_objects(BUCKET_NAME, recursive=True):
        # Only consider compressed files
        if not obj.object_name.lower().endswith(('.opus', '.flac')):
            continue
        
        # Use MinIO's last_modified time (when file was actually uploaded)
        now = datetime.now(timezone.utc)
        file_age_sec = (now - obj.last_modified).total_seconds()
        file_age_days = file_age_sec / 86400
        
        print(f"[CHECK] {obj.object_name}: {file_age_days:.1f} days old")
        
        if file_age_sec >= cutoff_sec:
            if dry_run:
                print(f"[DRY] Would delete: {obj.object_name} (stored for {file_age_days:.1f} days)")
            else:
                delete_object(obj.object_name)
                deleted += 1
                print(f"[DEL] Deleted: {obj.object_name} (stored for {file_age_days:.1f} days)")
    
    return deleted

def main():
    ap = argparse.ArgumentParser(
        description="Two-tier audio compression job - compresses files based on filename timestamp"
    )
    ap.add_argument(
        "--raw-max-age-days", 
        type=int, 
        default=DEFAULT_RAW_MAX_AGE_DAYS,
        help=f"Age threshold in days for audio files to be compressed (default: {DEFAULT_RAW_MAX_AGE_DAYS})"
    )
    ap.add_argument(
        "--codec", 
        choices=["opus", "flac"], 
        default=DEFAULT_LONG_TERM_CODEC,
        help="Compression codec to use"
    )
    ap.add_argument(
        "--compressed-max-age-days", 
        type=int, 
        default=DEFAULT_COMP_MAX_AGE_DAYS,
        help="Delete compressed files older than this many days (0 to disable)"
    )
    ap.add_argument(
        "--dry-run", 
        action="store_true",
        help="Simulate operations without making changes"
    )
    args = ap.parse_args()

    # Calculate age threshold
    raw_age_seconds = args.raw_max_age_days * 86400
    age_desc = f"{args.raw_max_age_days} days"

    print("=" * 70)
    print("AUDIO COMPRESSION & TIERING JOB")
    print("=" * 70)
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Age threshold: {age_desc} (based on filename timestamp)")
    print(f"Codec: {args.codec.upper()}")
    print(f"Compressed retention: {args.compressed_max_age_days} days")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 70)

    processed = 0
    skipped = 0
    errors = 0
    total_orig_size = 0
    total_comp_size = 0

    # Process audio files only
    for obj_name in iter_audio_files():
        
        # Check age based on filename timestamp
        age = get_file_age_seconds(obj_name)
        
        if age == 0:
            print(f"[SKIP] {obj_name} - Cannot parse timestamp from filename")
            skipped += 1
            continue
        
        if not is_older_than(obj_name, raw_age_seconds):
            skipped += 1
            continue
        
        age_days = age / 86400
        
        if args.dry_run:
            print(f"[DRY] Would compress: {obj_name} (age={age_days:.1f} days) -> {args.codec.upper()}")
            processed += 1
            continue

        # Get original size
        try:
            orig_stat = client.stat_object(BUCKET_NAME, obj_name)
            orig_size = orig_stat.size
            total_orig_size += orig_size
        except:
            orig_size = 0

        try:
            new_obj_name = encode_and_replace(obj_name, args.codec)
            
            # Get compressed size
            try:
                comp_stat = client.stat_object(BUCKET_NAME, new_obj_name)
                comp_size = comp_stat.size
                total_comp_size += comp_size
                saved = orig_size - comp_size
                ratio = orig_size / comp_size if comp_size > 0 else 0
                
                print(f"[OK] Compressed: {obj_name} -> {new_obj_name}")
                print(f"     Age: {age_days:.1f} days")
                print(f"     Original: {orig_size:,} bytes ({orig_size/(1024**2):.2f} MB)")
                print(f"     Compressed: {comp_size:,} bytes ({comp_size/(1024**2):.2f} MB)")
                print(f"     Ratio: {ratio:.2f}x, Saved: {saved:,} bytes ({saved/(1024**2):.2f} MB)")
            except:
                print(f"[OK] Compressed: {obj_name} -> {new_obj_name}")
            
            processed += 1

        except Exception as e:
            errors += 1
            print(f"[FAIL] {obj_name}: {e}")

    # Cleanup very old compressed files
    comp_deleted = cleanup_compressed(args.compressed_max_age_days, args.dry_run)

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Audio files compressed: {processed}")
    print(f"Files skipped (too new): {skipped}")
    print(f"Errors: {errors}")
    print(f"Old compressed deleted: {comp_deleted}")
    if total_orig_size > 0 and total_comp_size > 0:
        total_saved = total_orig_size - total_comp_size
        total_ratio = total_orig_size / total_comp_size
        print(f"Total original size: {total_orig_size:,} bytes ({total_orig_size/(1024**2):.2f} MB)")
        print(f"Total compressed size: {total_comp_size:,} bytes ({total_comp_size/(1024**2):.2f} MB)")
        print(f"Total saved: {total_saved:,} bytes ({total_saved/(1024**2):.2f} MB)")
        print(f"Overall compression ratio: {total_ratio:.2f}x")
    print("=" * 70)


if __name__ == "__main__":
    main()
