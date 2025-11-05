#!/bin/bash

SCRIPT_DIR="/app/src"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/tiering_$(date +%Y%m%d_%H%M%S).log"

mkdir -p "$LOG_DIR"
cd "$SCRIPT_DIR"

# In Docker, python3 is in PATH, no venv needed
PYTHON="python3"

# ffmpeg is already in PATH from Dockerfile
export PATH="/usr/bin:/usr/local/bin:$PATH"

echo "=== Starting at $(date) ===" >> "$LOG_FILE"
"$PYTHON" tiering_job.py \
    --raw-max-age-days ${RAW_MAX_AGE_DAYS:-30} \
    --codec ${COMPRESSION_CODEC:-opus} \
    --compressed-max-age-days ${COMPRESSED_MAX_AGE_DAYS:-90} \
    >> "$LOG_FILE" 2>&1
echo "=== Finished at $(date) ===" >> "$LOG_FILE"

# Clean old logs (older than 7 days)
find "$LOG_DIR" -name "tiering_*.log" -mtime +7 -delete
