from pathlib import Path
import time
import csv
import psutil
import subprocess
from statistics import mean

# Import from local prototype library
from prototype_lib import iter_input_files, build_ffmpeg_cmds, ROOT

# Results directory
RES_DIR = ROOT / "results"
RES_DIR.mkdir(parents=True, exist_ok=True)


def file_size(p: Path) -> int:
    """Return file size in bytes if exists, else 0."""
    return p.stat().st_size if p.exists() else 0


def run_and_profile(cmd):
    """
    Run the encode command and sample CPU usage while it runs.

    Returns:
        (returncode, wall_time_sec, avg_cpu_percent, combined_output)
    """
    start = time.time()
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    parent = psutil.Process(proc.pid)

    samples = []
    time.sleep(0.05)  # small warmup

    while proc.poll() is None:
        cpu_total = 0.0
        try:
            procs = [parent] + parent.children(recursive=True)
            for pr in procs:
                try:
                    cpu_total += pr.cpu_percent(interval=0.1)
                except psutil.NoSuchProcess:
                    pass
        except psutil.NoSuchProcess:
            pass
        samples.append(cpu_total)

    out, err = proc.communicate()
    wall = time.time() - start
    avg_cpu = mean(samples) if samples else 0.0
    return proc.returncode, wall, avg_cpu, (out or "") + (err or "")


def main():
    rows = []
    files = list(iter_input_files())

    if not files:
        print("No input audio files found in data/raw/")
        return

    for f in files:
        orig_size = file_size(f)

        # Encode with each codec
        for codec, cmd, outp in build_ffmpeg_cmds(f):
            rc, wall, cpu, _ = run_and_profile(cmd)
            if rc != 0:
                print(f"[FAIL] {f.name} ({codec})")
                continue

            enc_size = file_size(outp)
            ratio = (orig_size / enc_size) if enc_size else 0.0

            print(
                f"[OK] {f.name} | {codec.upper()}: "
                f"{enc_size} bytes, {wall:.2f}s, CPU~{cpu:.1f}% (ratio={ratio:.3f})"
            )

            rows.append({
                "file": f.name,
                "codec": codec,
                "orig_bytes": orig_size,
                "encoded_bytes": enc_size,
                "compression_ratio_orig_over_encoded": round(ratio, 3),
                "encode_time_sec": round(wall, 3),
                "encode_cpu_avg_percent": round(cpu, 1),
            })

    if rows:
        out_csv = RES_DIR / "benchmarks.csv"
        with open(out_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        print(f"Saved CSV: {out_csv}")
    else:
        print("No rows to save (no successful encodes).")


if __name__ == "__main__":
    main()
