#!/bin/bash
set -e

# Fix permissions for secrets directory if it exists (runs as root)
if [ -d "/opt/app/secrets" ]; then
    echo "Fixing permissions for /opt/app/secrets..."
    chown -R flink:flink /opt/app/secrets
    chmod 775 /opt/app/secrets
fi

# Call the original Flink entrypoint
exec /docker-entrypoint.sh "$@"
