# ============================
# Stage 1: get mc binary
# ============================
FROM minio/mc:latest AS mc-source

# ============================
# Stage 2: main image
# ============================
FROM alpine:3.19

# Install base tools
RUN apk add --no-cache \
  bash \
  curl \
  ca-certificates \
  netcat-openbsd \
  dos2unix && \
  update-ca-certificates

# ===== Add NetFree CA =====
RUN mkdir -p /usr/local/share/ca-certificates
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates || true

# ----------------------------
# Install mc (MinIO client)
# ----------------------------
COPY --from=mc-source /usr/bin/mc /usr/local/bin/mc
RUN chmod +x /usr/local/bin/mc

# ----------------------------
# Entrypoint script
# ----------------------------
RUN mkdir -p /entrypoint /config
COPY entrypoint/init.sh /entrypoint/init.sh
RUN dos2unix /entrypoint/init.sh && chmod 755 /entrypoint/init.sh

CMD ["/entrypoint/init.sh"]
