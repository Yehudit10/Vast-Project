#!/usr/bin/env bash
set -euo pipefail

echo "[$(date -Iseconds)] [plant_stress_daily] starting job..."
python -u /app/src/predict_minio_daily.py
echo "[$(date -Iseconds)] [plant_stress_daily] finished job."
