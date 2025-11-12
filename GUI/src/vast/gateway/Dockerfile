# syntax=docker/dockerfile:1.6

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
# build arg
# ARG USE_NETFREE=true

# Toggle NetFree handling at build time:
#   docker build --build-arg USE_NETFREE=true  -t image:netfree .
#   docker build --build-arg USE_NETFREE=false -t image:default .
ARG USE_NETFREE=false

# Base system tools (certificates + curl)
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# Conditionally load extra CA certs from build context ./certs (if exists)
# - With BuildKit, the mount is optional (required=false).
# - If USE_NETFREE=false or no *.crt files exist, nothing happens.
RUN --mount=type=bind,source=certs,target=/tmp/certs,required=false \
    set -eux; \
    if [ "${USE_NETFREE}" = "true" ] \
       && [ -d /tmp/certs ] \
       && ls /tmp/certs/*.crt >/dev/null 2>&1; then \
        echo "Adding extra CA certs from /tmp/certs ..."; \
        cp /tmp/certs/*.crt /usr/local/share/ca-certificates/; \
        update-ca-certificates; \
    else \
        echo "No extra CA certs configured (USE_NETFREE=${USE_NETFREE})."; \
    fi

# System-wide SSL env (works with or without extra CAs)
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Python dependencies


# # System CA + add NetFree certs
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY certs/*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates || true
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt \
    --index-url https://pypi.org/simple \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org

# App code
COPY src/vast/gateway /app/vast/gateway
COPY src/vast/proto   /app/vast/proto

# Generate gRPC stubs
RUN python -m grpc_tools.protoc -I./vast/proto \
    --python_out=. --grpc_python_out=. \
    ./vast/proto/query.proto

ENV PYTHONPATH=/app/vast/proto/generated:/app
ENV RUNNER_ADDR=runner:50051

EXPOSE 8000
CMD ["uvicorn", "vast.gateway.gateway_main:app", "--host", "0.0.0.0", "--port", "8000"]
