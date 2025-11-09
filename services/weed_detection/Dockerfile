# ---- Base: lightweight Python + Torch CPU ----
FROM python:3.10-slim

ARG DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1

# System and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl build-essential gcc libpq5 git && \
    rm -rf /var/lib/apt/lists/*

# NetFree CA
COPY certs/netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN update-ca-certificates

# Make pip/requests use the system CA bundle
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# NEW: install certifi and replace it with the system bundle
RUN python -m pip install --upgrade pip certifi && python - <<'PY'
import certifi, shutil, os
src = "/etc/ssl/certs/ca-certificates.crt"
dst = certifi.where()
os.makedirs(os.path.dirname(dst), exist_ok=True)
shutil.copyfile(src, dst)
print("certifi bundle replaced:", dst)
PY

# Install PyTorch CPU (2.9.0) + torchvision (0.24.0) from the PyTorch index
RUN pip install "torch==2.9.0+cpu" "torchvision==0.24.0+cpu" --index-url https://download.pytorch.org/whl/cpu

# Other dependencies — excluding torch/torchvision/torchaudio
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN sed -i '/^torch/d;/^torchvision/d;/^torchaudio/d' /tmp/requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Code and execution
COPY . .
CMD ["python", "-m", "scripts.run_detection", "--storage", "minio"]
