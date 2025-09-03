# Sound 2 – Compression & Retention Policy

## Implements

1. Prototype compression (FLAC, Opus).
2. Measure compression ratio, encoding time, CPU usage.
3. Two-tier storage: `data/raw` (short-term) → `data/compressed` (long-term) with retention.

## Layout

- `data/raw/` – input audio.
- `data/compressed/` – compressed outputs.
- `results/` – benchmark results.
- `scripts/` – Python code.

## Usage

```bash
# Python
pip install psutil pandas
python scripts/prototype_lib.py
python scripts/run_bench.py
python scripts/tiering_job.py --raw-max-age-hours 24 --codec opus --delete-raw-after --compressed-max-age-days 90
```

## Notes - compression task

- FLAC = lossless, may be larger than MP3.

- Opus = smaller, low-loss, higher CPU.

- Retention controlled with --compressed-max-age-days.
