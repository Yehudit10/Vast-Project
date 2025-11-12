FROM mcr.microsoft.com/devcontainers/python:1-3.11-bullseye

WORKDIR /app

# 1) Install CA tools and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# 2) Add NetFree certificate and register in system trust store

# Ensure Python, requests, and pip use the updated CA bundle
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# 3) Install Python dependencies (use trusted hosts to simplify NetFree path)
COPY requirements.txt /app/requirements.txt
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org --no-cache-dir -r requirements.txt

# 4) Install the package (PEP517) with the same trusted hosts
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org --no-cache-dir .

# 5) Copy configs (can be overridden by a bind mount)
COPY configs /app/configs

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "-m", "disease_monitor.cli"]

