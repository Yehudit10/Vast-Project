FROM python:3.11-slim

# Tools+certs first
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# MinIO server binary
RUN curl -k -L -o /usr/local/bin/minio https://dl.min.io/server/minio/release/linux-amd64/minio \
    && chmod +x /usr/local/bin/minio

# Python SDK
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --no-cache-dir minio

# App
WORKDIR /app
COPY create_buckets.py /app/create_buckets.py
RUN mkdir -p /data

EXPOSE 9000 9001

CMD sh -c 'minio server /data --console-address :9001 & \
    echo "Waiting for MinIO..." && sleep 5 && \
    python3 /app/create_buckets.py && \
    tail -f /dev/null'