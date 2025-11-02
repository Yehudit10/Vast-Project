FROM python:3.11-slim

# Tools+certs first
RUN apt-get update \

&& apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

## Adding a NetFri certificate
COPY certs/*.crt /usr/local/share/ca-certificates/
RUN chmod 644 /usr/local/share/ca-certificates/*.crt \
 && update-ca-certificates

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

ARG MINIO_URL="https://dl.min.io/server/minio/release/linux-amd64/minio"
ARG MINIO_SHA256=""
RUN set -eux; \
  tmp="/usr/local/bin/minio.part"; \
  out="/usr/local/bin/minio"; \
  for i in $(seq 1 10); do \
    curl -fL --http1.1 --retry 10 --retry-all-errors --retry-delay 5 \
         --connect-timeout 20 --max-time 0 \
         -o "$tmp" "$MINIO_URL" \
    && test -s "$tmp" && break || sleep 5; \
  done; \
  mv "$tmp" "$out"; \
  chmod +x "$out"; \
  if [ -n "$MINIO_SHA256" ]; then \
    echo "${MINIO_SHA256}  ${out}" | sha256sum -c -; \
  fi

# MinIO server binary
# RUN curl -fL --retry 5 --retry-delay 5 \
#     -o /usr/local/bin/minio \
#     https://dl.min.io/server/minio/release/linux-amd64/minio \
#  && chmod +x /usr/local/bin/minio

#     && apt-get install -y --no-install-recommends curl ca-certificates \
#     && rm -rf /var/lib/apt/lists/*

# # MinIO server binary
# RUN curl -k -L -o /usr/local/bin/minio https://dl.min.io/server/minio/release/linux-amd64/minio \
#     && chmod +x /usr/local/bin/minio

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