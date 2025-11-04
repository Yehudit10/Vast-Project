# ===============================
# Base image
# ===============================
FROM python:3.11-slim

# Basic Python and pip environment configuration
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=1200 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app


# ===============================
# NetFree certificate setup
# ===============================
# Install system certificates and curl (required for HTTPS connections)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Copy your NetFree ca certificate into the container
# Make sure you have a folder "certs" with file "netfree-ca.crt" next to this Dockerfile
COPY certs/netfree-ca.crt /usr/local/share/ca-certificates/

# Register the new certificate into the system ca store
RUN update-ca-certificates || true

# Tell all Python libraries (pip, requests, urllib3) to use this CA certificate
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt


# ===============================
# Install Python dependencies
# ===============================
# Upgrade pip and install numpy first (binary-only to reduce build time)
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir numpy==1.26.4 --only-binary=:all:

# Install PyTorch CPU version (avoid GPU dependency)
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.2 torchvision==0.16.2 --only-binary=:all: --upgrade-strategy only-if-needed

# Copy requirements file and install remaining dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    --only-binary=:all: --upgrade-strategy only-if-needed \
    --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org


# ===============================
# Copy source code
# ===============================
COPY app.py model_registry.py /app/
COPY adapters /app/adapters
COPY models   /app/models


# ===============================
# Runtime configuration
# ===============================
# Expose the FastAPI/uvicorn port
EXPOSE 8000

# Launch the application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
