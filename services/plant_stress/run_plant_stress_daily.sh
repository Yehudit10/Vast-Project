#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/mnt/c/Users/This User/Desktop/New folder/AgCloud"
LOG_DIR="$PROJECT_DIR/services/plant_stress/logs"
STAMP="$(date +%F)"
LOG_FILE="$LOG_DIR/cron_${STAMP}.log"

mkdir -p "$LOG_DIR"

echo "[cron start $(date '+%Y-%m-%d %H:%M:%S')]" >> "$LOG_FILE"

cd "$PROJECT_DIR"

exec /usr/bin/docker compose run --rm plant_stress_daily >> "$LOG_FILE" 2>&1
