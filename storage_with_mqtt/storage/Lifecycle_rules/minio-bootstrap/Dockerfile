# ============================
# Stage 1: copy mc binary
# ============================
FROM minio/mc:latest AS mc-source

# ============================
# Stage 2: main image
# ============================
FROM alpine:3.19

# ===== Install dependencies =====
RUN apk add --no-cache bash curl ca-certificates netcat-openbsd && \
  update-ca-certificates

# ===== Add NetFree CA =====
COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN update-ca-certificates

# ===== Copy mc from the official image =====
COPY --from=mc-source /usr/bin/mc /usr/local/bin/mc
RUN chmod +x /usr/local/bin/mc

# ===== Create directories =====
RUN mkdir -p /entrypoint /config

# ===== Copy init script ===== 
COPY entrypoint/init.sh /entrypoint/init.sh
RUN chmod +x /entrypoint/init.sh

# ===== Entry point =====
CMD ["/entrypoint/init.sh"]
