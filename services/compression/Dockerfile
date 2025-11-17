FROM python:3.12-slim

# Install ffmpeg, cron, and ca-certificates
RUN apt-get update && \
    apt-get install -y ffmpeg cron ca-certificates dos2unix && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy certificates
COPY certs /app/certs

# Install certificates
RUN cp /app/certs/*.crt /usr/local/share/ca-certificates/ && \
update-ca-certificates

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Create logs directory
RUN mkdir -p /app/src/logs

# Copy and fix both scripts
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN dos2unix /docker-entrypoint.sh && \
    chmod +x /docker-entrypoint.sh && \
    dos2unix /app/src/run_tiering.sh && \
    chmod +x /app/src/run_tiering.sh

WORKDIR /app/src

ENTRYPOINT ["/docker-entrypoint.sh"]
