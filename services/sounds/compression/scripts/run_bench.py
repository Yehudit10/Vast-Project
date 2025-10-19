from pathlib import Path
import time
import csv
from statistics import mean
import subprocess
from prototype_lib import iter_input_files, build_ffmpeg_cmds, download_raw_to_temp, upload_compressed, delete_object
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
    files = list(iter_input_files())
    if not files:
        print("No raw files found in MinIO")
        return

    for obj_name in files:
        local_file = download_raw_to_temp(obj_name)
        orig_size = local_file.stat().st_size

        for codec, cmd, outp in build_ffmpeg_cmds(local_file):
            rc, wall, cpu, _ = run_and_profile(cmd)
            if rc != 0:
                print(f"[FAIL] {obj_name} ({codec})")
                continue

            target_obj = upload_compressed(outp)
            enc_size = file_size_minio(target_obj)
            ratio = (orig_size / enc_size) if enc_size else 0.0

            print(f"[OK] {obj_name} | {codec.upper()}: {enc_size} bytes, {wall:.2f}s, CPU~{cpu:.1f}% (ratio={ratio:.3f})")

            rows.append({
                "file": Path(obj_name).name,
                "codec": codec,
                "orig_bytes": orig_size,
                "encoded_bytes": enc_size,
                "compression_ratio_orig_over_encoded": round(ratio, 3),
                "encode_time_sec": round(wall, 3),
                "encode_cpu_avg_percent": round(cpu, 1),
            })

            # Clean up local encoded file
            outp.unlink()

        local_file.unlink()

    if rows:
        out_csv = RES_DIR / "benchmarks.csv"
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved CSV: {out_csv}")

if __name__ == "__main__":
    main()