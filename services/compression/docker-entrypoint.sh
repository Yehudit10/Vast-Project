#!/bin/bash
set -e

echo "Setting up cron job..."

# Write environment variables with export prefix
printenv | grep -E '^(RAW_MAX_AGE_DAYS|COMPRESSION_CODEC|COMPRESSED_MAX_AGE_DAYS|MINIO_ENDPOINT|ACCESS_KEY|SECRET_KEY|BUCKET_NAME)=' | sed 's/^/export /' > /app/cron.env

# Make scripts executable
chmod +x /app/src/run_tiering.sh

# Create crontab
cat > /tmp/crontab.txt << 'EOF'
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/sbin:/usr/sbin:/sbin

# Run every 2 minutes
*/2 * * * * . /app/cron.env && /app/src/run_tiering.sh >> /app/src/logs/cron.log 2>&1

# Debug: Log cron is alive every 10 minutes
*/10 * * * * echo "[$(date)] Cron is alive" >> /app/src/logs/cron.log
EOF

# Install crontab
crontab /tmp/crontab.txt

echo "==================================="
echo "Audio Compression Service Started"
echo "==================================="
echo "Cron schedule:"
crontab -l
echo "==================================="
echo "Environment variables saved to /app/cron.env:"
cat /app/cron.env
echo "==================================="

# Create logs directory
mkdir -p /app/src/logs

# Initial log entry
echo "[$(date)] Cron daemon starting..." >> /app/src/logs/cron.log

echo "Waiting for MinIO to be ready..."
sleep 10

echo "==================================="
echo "Running initial test..."
echo "==================================="

# Run initial test (this will show if there are any immediate errors)
if /app/src/run_tiering.sh >> /app/src/logs/cron.log 2>&1; then
    echo "✓ Initial test completed successfully"
else
    echo "✗ Initial test failed - check /app/src/logs/cron.log"
fi

echo "==================================="
echo "Service is now running."
echo "Compression will run every 2 minutes."
echo "Check logs: docker exec audio_compression tail -f /app/src/logs/cron.log"
echo "==================================="

# Start cron in foreground
exec cron -f