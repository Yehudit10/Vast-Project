# syntax=docker/dockerfile:1
FROM flink:1.19.3-scala_2.12-java11

USER root
WORKDIR /opt/app

# -----------------------------
# System CA & Python toolchain
# -----------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates wget curl python3 python3-venv python3-pip jq gnupg \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------
# Optional NetFree CAs (empty dir is OK)
# If you have custom CAs, put *.crt in ./certs and they will be added.
# -----------------------------
COPY certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates || true

# -----------------------------
# SSL env for pip/requests (works with/without NetFree)
# -----------------------------
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# -----------------------------
# Optional PyPI mirror (for NetFree or internal mirror)
# Pass --build-arg PIP_INDEX_URL=https://<mirror>/simple
# -----------------------------
ARG PIP_INDEX_URL=""
RUN set -eux; \
  mkdir -p /etc/pip; \
  { \
    echo "[global]"; \
    echo "cert = /etc/ssl/certs/ca-certificates.crt"; \
    echo "trusted-host = pypi.org"; \
    echo "trusted-host = files.pythonhosted.org"; \
  } > /etc/pip/pip.conf; \
  if [ -n "$PIP_INDEX_URL" ]; then \
    echo "index-url = $PIP_INDEX_URL" >> /etc/pip/pip.conf; \
  fi

# -----------------------------
# Python venv (expose system packages as fallback)
# -----------------------------
RUN python3 -m venv /opt/venv --system-site-packages
ENV PATH="/opt/venv/bin:${PATH}"

# -----------------------------
# Copy requirements and install (pip first, apt fallback for some libs)
# -----------------------------
COPY requirements.txt /opt/app/requirements.txt

# Optional: allow passing a pre-downloaded PyFlink wheel (for NetFree)
ARG PYFLINK_WHEEL_URL=""
# Make sure shell sees a defined variable even with `set -u`
ENV PYFLINK_WHEEL_URL="${PYFLINK_WHEEL_URL}"

RUN set -eux; \
  python -m pip install --no-cache-dir --upgrade \
    --trusted-host pypi.org --trusted-host files.pythonhosted.org \
    --cert /etc/ssl/certs/ca-certificates.crt \
    pip setuptools wheel; \
  echo ">>> Installing Python deps via pip (requirements.txt)"; \
  if ! python -m pip install --no-cache-dir \
        --trusted-host pypi.org --trusted-host files.pythonhosted.org \
        --cert /etc/ssl/certs/ca-certificates.crt \
        -r /opt/app/requirements.txt; then \
    echo "WARN: pip install failed or blocked; trying apt fallback for core libs"; \
    apt-get update && apt-get install -y --no-install-recommends \
      python3-yaml python3-protobuf python3-grpcio \
      && rm -rf /var/lib/apt/lists/*; \
  fi; \
  echo '>>> Ensuring requests is installed (pip first, apt fallback)'; \
  if ! python -m pip install --no-cache-dir \
        --trusted-host pypi.org --trusted-host files.pythonhosted.org \
        --cert /etc/ssl/certs/ca-certificates.crt \
        requests==2.32.3; then \
    echo 'WARN: pip blocked for requests; falling back to apt'; \
    apt-get update && apt-get install -y --no-install-recommends python3-requests || true; \
    rm -rf /var/lib/apt/lists/*; \
  fi; \
  echo ">>> Enforcing PyFlink presence (wheel or pip)"; \
  if [ -n "${PYFLINK_WHEEL_URL:-}" ]; then \
    python -m pip install --no-cache-dir \
      --cert /etc/ssl/certs/ca-certificates.crt "${PYFLINK_WHEEL_URL}" \
      || (echo 'FATAL: PyFlink wheel install failed' && exit 1); \
  else \
    python -m pip install --no-cache-dir \
      --trusted-host pypi.org --trusted-host files.pythonhosted.org \
      --cert /etc/ssl/certs/ca-certificates.crt \
      apache-flink==1.19.3 \
      || (echo 'FATAL: apache-flink install failed' && exit 1); \
  fi; \
  echo ">>> Forcing critical runtime libs into venv (pip first, apt fallback)"; \
  if ! python -m pip install --no-cache-dir \
        --trusted-host pypi.org --trusted-host files.pythonhosted.org \
        --cert /etc/ssl/certs/ca-certificates.crt \
        protobuf==4.25.3 googleapis-common-protos==1.63.0 grpcio==1.60.0; then \
    echo "WARN: pip blocked for key libs; using apt fallback"; \
    apt-get update && apt-get install -y --no-install-recommends \
      python3-protobuf python3-grpcio || true; \
    rm -rf /var/lib/apt/lists/*; \
  fi; \
  python - <<'PY'
import sys
print("Python:", sys.version)
# hard fail if imports are not available inside the venv
for mod in ("requests", "urllib3", "google", "google.protobuf", "grpc", "pyflink"):
    try:
        __import__(mod)
        print(mod, "OK")
    except Exception as e:
        print("FATAL import check:", mod, "->", e)
        raise SystemExit(1)
PY


# -----------------------------
# Flink Kafka connector jars (REQUIRED for Kafka in cluster mode)
# Version aligned to Flink 1.19
# -----------------------------
RUN mkdir -p /opt/flink/lib && \
    wget -qO /opt/flink/lib/flink-connector-kafka-3.2.0-1.19.jar \
      https://repo1.maven.org/maven2/org/apache/flink/flink-connector-kafka/3.2.0-1.19/flink-connector-kafka-3.2.0-1.19.jar && \
    wget -qO /opt/flink/lib/kafka-clients-3.7.0.jar \
      https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.7.0/kafka-clients-3.7.0.jar

# -----------------------------
# Copy app code (keep small, configurable by ENV)
# -----------------------------
COPY config.py     /opt/app/config.py
COPY processor.py  /opt/app/processor.py
COPY flink_job.py  /opt/app/flink_job.py

# -----------------------------
# Runtime ENV defaults (can be overridden in docker-compose)
# -----------------------------
ENV PYTHONPATH=/opt/app \
    PYFLINK_CLIENT_EXECUTABLE=python \
    PYFLINK_PYTHON=python \
    KAFKA_BROKERS=kafka:9092 \
    SOURCE_TOPIC=sound.new.sounds \
    SINK_TOPIC=classified.sounds \
    GROUP_ID=flink-classifier-sounds \
    KAFKA_START=earliest

# -----------------------------
# Default CMD is noop; compose sets jobmanager/taskmanager/submitter commands
# -----------------------------
CMD ["bash", "-lc", "echo 'Flink image ready (NetFree/Non-NetFree compatible)'; tail -f /dev/null"]
