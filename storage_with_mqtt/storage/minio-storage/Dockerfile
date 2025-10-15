FROM python:3.11-slim

# Tools+certs first
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# # Adding a NetFri certificate
COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt \
 && update-ca-certificates

# MinIO server binary
RUN curl -k -L -o /usr/local/bin/minio https://dl.min.io/server/minio/release/linux-amd64/minio \
 && chmod +x /usr/local/bin/minio

# Python SDK
# RUN pip install  minio
COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
    && update-ca-certificates
RUN python -m pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org minio


# App
WORKDIR /app
COPY create_buckets.py /app/create_buckets.py
RUN mkdir -p /data

EXPOSE 9000 9001

CMD sh -c 'minio server /data --console-address :9001 & \
           echo "Waiting for MinIO..." && sleep 5 && \
           python3 /app/create_buckets.py && \
           tail -f /dev/null'

