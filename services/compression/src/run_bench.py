from pathlib import Path
import time
import csv
from statistics import mean
import subprocess
from prototype_lib import (
    iter_audio_files,
    build_ffmpeg_cmds,
    download_raw_to_temp,
    replace_with_compressed,
    parse_timestamp_from_filename,
    get_file_age_seconds
)
from minio_client import BUCKET_NAME, client

RES_DIR = Path("results")
RES_DIR.mkdir(exist_ok=True)

def file_size_minio(obj_name: str) -> int:
    """Return object size in bytes."""
    try:
        stat = client.stat_object(BUCKET_NAME, obj_name)
        return stat.size
    except:
        return 0

def run_and_profile(cmd):
    """Run command and profile CPU usage."""
    import psutil
    start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    parent = psutil.Process(proc.pid)
    samples = []
    while proc.poll() is None:
        cpu_total = 0.0
        for pr in [parent] + parent.children(recursive=True):
            try:
                cpu_total += pr.cpu_percent(interval=0.1)
            except psutil.NoSuchProcess:
                continue
        samples.append(cpu_total)
    out, err = proc.communicate()
    wall = time.time() - start
    avg_cpu = mean(samples) if samples else 0.0
    return proc.returncode, wall, avg_cpu, (out or b"") + (err or b"")

def main():
    rows = []
    files = list(iter_audio_files())
    if not files:
        print("No audio files found in MinIO")
        return

    print("=" * 70)
    print("AUDIO COMPRESSION BENCHMARK")
    print("=" * 70)
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Files to process: {len(files)}")
    print("=" * 70)

    for obj_name in files:
        # Parse timestamp from filename
        dt = parse_timestamp_from_filename(obj_name)
        age_seconds = get_file_age_seconds(obj_name)
        
        print(f"\n[PROCESSING] {obj_name}")
        if dt:
            print(f"  Timestamp: {dt.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            print(f"  Age: {age_seconds/86400:.1f} days")
        
        # Download original file
        local_file = download_raw_to_temp(obj_name)
        orig_size = local_file.stat().st_size

        # Test each codec
        for codec, cmd, outp in build_ffmpeg_cmds(local_file):
            rc, wall, cpu, _ = run_and_profile(cmd)
            if rc != 0:
                print(f"  [FAIL] {codec.upper()} encoding failed")
                continue

            # Replace original with compressed version (same path, different extension)
            try:
                new_obj_name = replace_with_compressed(obj_name, outp)
                enc_size = file_size_minio(new_obj_name)
                ratio = (orig_size / enc_size) if enc_size else 0.0

                print(f"  [OK] {codec.upper()}: {new_obj_name}")
                print(f"       Size: {enc_size:,} bytes ({enc_size/(1024**2):.2f} MB)")
                print(f"       Ratio: {ratio:.2f}x")
                print(f"       Time: {wall:.2f}s, CPU: {cpu:.1f}%")

                rows.append({
                    "file": Path(obj_name).name,
                    "codec": codec,
                    "orig_bytes": orig_size,
                    "encoded_bytes": enc_size,
                    "compression_ratio_orig_over_encoded": round(ratio, 3),
                    "encode_time_sec": round(wall, 3),
                    "encode_cpu_avg_percent": round(cpu, 1),
                    "timestamp": dt.isoformat() if dt else "unknown",
                    "age_days": round(age_seconds / 86400, 1) if age_seconds > 0 else 0,
                })

                # Clean up local encoded file
                outp.unlink()
                
            except Exception as e:
                print(f"  [FAIL] {codec.upper()}: {e}")
                outp.unlink(missing_ok=True)

        # Clean up local original file
        local_file.unlink()

    # Save results
    if rows:
        out_csv = RES_DIR / "benchmarks.csv"
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"Total files benchmarked: {len(files)}")
        print(f"Total tests: {len(rows)}")
        print(f"Results saved: {out_csv}")
        print("=" * 70)
    else:
        print("\n[WARN] No successful encodings to save")

if __name__ == "__main__":
    main()