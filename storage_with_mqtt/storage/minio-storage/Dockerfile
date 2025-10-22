FROM python:3.11-slim
# Tools+certs first
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
## Adding a NetFri certificate
# COPY *.crt /usr/local/share/ca-certificates/netfree-ca.crt
# RUN chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt \
#  && update-ca-certificates

COPY certs/*.crt /usr/local/share/ca-certificates/
RUN chmod 644 /usr/local/share/ca-certificates/*.crt \
 && update-ca-certificates

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

# MinIO server binary
RUN curl -fL --retry 5 --retry-delay 5 \
    -o /usr/local/bin/minio \
    https://dl.min.io/server/minio/release/linux-amd64/minio \
 && chmod +x /usr/local/bin/minio
# RUN curl -L -o /usr/local/bin/minio https://dl.min.io/server/minio/release/linux-amd64/minio \
#  && chmod +x /usr/local/bin/minio

# Python SDK
RUN pip install --no-cache-dir minio
# RUN pip install  minio

# App
WORKDIR /app
COPY create_buckets.py /app/create_buckets.py
RUN mkdir -p /data
EXPOSE 9000 9001
CMD sh -c 'minio server /data --console-address :9001 & \
           echo "Waiting for MinIO..." && sleep 5 && \
           python3 /app/create_buckets.py && \
           tail -f /dev/null'