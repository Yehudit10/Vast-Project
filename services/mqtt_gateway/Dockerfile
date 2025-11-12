# syntax=docker/dockerfile:1
FROM python:3.12-slim

ARG USE_NETFREE=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libc6 libsasl2-2 libssl3 librdkafka1 \
  && rm -rf /var/lib/apt/lists/*

# (Optional) import NetFree cert if present in build context
RUN if [ "$USE_NETFREE" = "true" ] && [ -f ./netfree-ca.crt ]; then \
      cp ./netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt && \
      chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt && \
      update-ca-certificates; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
# COPY services/mqtt_gateway/requirements.txt .
COPY requirements.txt .
RUN pip install --no-cache-dir --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt

# COPY services/mqtt_gateway /app/services/mqtt_gateway
COPY . /app/services/mqtt_gateway


# Default envs (override in deployment)
ENV MINIO_ENDPOINT=http://minio:9000 \
    MINIO_ACCESS_KEY=minioadmin \
    MINIO_SECRET_KEY=minioadmin \
    MINIO_BUCKET=rover-images \
    KAFKA_BOOTSTRAP=kafka:9092 \
    KAFKA_TOPIC=rover.images.meta.v1 \
    MQTT_HOST=mosquitto \
    MQTT_PORT=1883 \
    MQTT_TOPIC=MQTT/imagery/# \
    MQTT_CLIENT_ID=mqtt-gateway

CMD ["python", "-m", "services.mqtt_gateway.main"]
