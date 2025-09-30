# Sound 2 – Compression & Retention Policy

## Implements

1. Prototype compression (FLAC, Opus).
2. Measure compression ratio, encoding time, CPU usage.
3. Two-tier storage: `data/raw` (short-term) → `data/compressed` (long-term) with retention, directly on MinIO.

## MionIO Layout

- Bucket: compression
- Folder raw/ – input audio.
- Folder compressed/ – compressed outputs.
- results/ – benchmark results (local).
- scripts/ – Python code.

## Usage

```bash
# Python
pip install psutil pandas minio

# Benchmarks: encode all raw files and measure CPU/time/ratio
python scripts/run_bench.py

# Tiering job: compress raw files older than 24h, encode to Opus, delete raw, retention 90 days
python scripts/tiering_job.py --raw-max-age-hours 24 --codec opus --delete-raw-after --compressed-max-age-days 90

# Dry run example
python scripts/tiering_job.py --raw-max-age-hours 24 --codec opus --dry-run
```

## Notes - compression task

- FLAC = lossless, may be larger than MP3.

- Opus = smaller, low-loss, higher CPU.

- Retention controlled with --compressed-max-age-days.

- All files are stored directly on MinIO, no local copy required.

## MinIO Client Configuration

```bash
client = Minio(
    "localhost:9001",
    access_key="minioadmin",
    secret_key="minioadmin123",
    secure=False
)
```
