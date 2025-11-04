FROM python:3.12-slim

# Install ffmpeg, cron, and ca-certificates
RUN apt-get update && \
    apt-get install -y ffmpeg cron ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy certificates to container (make sure the 'certs' folder contains the necessary .crt files)
COPY certs /app/certs

# Install necessary certificates and add custom ones
RUN cp /app/certs/*.crt /usr/local/share/ca-certificates/ && \
    update-ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code to the container
COPY src/ ./src/

# Create logs directory
RUN mkdir -p /app/src/logs

# Copy cron setup script
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

WORKDIR /app/src

# Run cron in foreground
ENTRYPOINT ["/docker-entrypoint.sh"]
