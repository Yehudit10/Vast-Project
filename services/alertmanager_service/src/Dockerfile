# ─────────────────────────────────────────────
# Dockerfile (used for both alert_service and gateway)
# ─────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Copy code
COPY . .

# Install deps
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pyyaml aiohttp asyncpg


# Default port — can be overridden by compose
EXPOSE 8090

# Default environment
ENV CFG_PATH=/app/templates.yml
ENV ALERTMANAGER_URL=http://alertmanager:9093
ENV GATEWAY_URL=http://alerts-gateway:8000/internal/alert


# Default command (can be overridden in docker-compose)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
