# ============================================================
# Unified Inference HTTP Dockerfile (Fruit + Camera + YOLO)
# ============================================================
FROM python:3.11-slim



ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=1200


WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libglib2.0-dev \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgl1 \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel --only-binary=:all: && \
    pip install --no-cache-dir numpy==1.26.4 --only-binary=:all: && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==2.1.2 torchvision==0.16.2 --only-binary=:all: --upgrade-strategy only-if-needed


ENV PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=1200 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy certs dir (may be empty) and trust *.crt if present
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/* && \
    if [ -d /tmp/certs ] && ls /tmp/certs/*.crt >/dev/null 2>&1; then \
    cp /tmp/certs/*.crt /usr/local/share/ca-certificates/ && \
    chmod 644 /usr/local/share/ca-certificates/*.crt && \
    update-ca-certificates; \
    else \
    echo "No extra CA certs found. Skipping CA update."; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt
RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

# Python deps
RUN python -m pip install --upgrade pip setuptools wheel certifi && \
    pip install --no-cache-dir numpy==1.26.4 --only-binary=:all:

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.2 torchvision==0.16.2 --only-binary=:all: --upgrade-strategy only-if-needed

COPY requirements.txt /app/requirements.txt


RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir \
        opencv-python-headless \
        ultralytics==8.2.34 \
        boto3 \
        pillow \
        requests \
        "numpy<2" \
        && rm -rf /root/.cache/pip


COPY app.py model_registry.py /app/
COPY adapters /app/adapters
COPY models /app/models
COPY weights /app/weights
COPY models/soil_moisture/artifacts /app/artifacts

EXPOSE 8004

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8004"]
