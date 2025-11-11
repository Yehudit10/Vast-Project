# ============================
# Stage 1: copy mc binary
# ============================
FROM minio/mc:latest AS mc-source

# ============================
# Stage 2: main image
# ============================
FROM alpine:3.19

# ===== Install dependencies =====
# include dos2unix so line endings are normalized automatically
RUN apk add --no-cache bash curl ca-certificates netcat-openbsd dos2unix && \
  update-ca-certificates

# ===== Add NetFree CA =====
# COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
# RUN update-ca-certificates
COPY certs/*.crt /usr/local/share/ca-certificates/
RUN chmod 644 /usr/local/share/ca-certificates/*.crt \
 && update-ca-certificates


# ===== Copy mc from the official image =====
COPY --from=mc-source /usr/bin/mc /usr/local/bin/mc
RUN chmod +x /usr/local/bin/mc

# ===== Create directories =====
RUN mkdir -p /entrypoint /config

# ===== Copy init script ===== 
COPY entrypoint/init.sh /entrypoint/init.sh

# ===== Normalize and ensure execution permissions =====
# (this guarantees LF endings + execute permission for everyone)
RUN dos2unix /entrypoint/init.sh && chmod 755 /entrypoint/init.sh

# ===== Entry point =====
CMD ["/entrypoint/init.sh"]
