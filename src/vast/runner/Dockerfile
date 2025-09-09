FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# System CA + NetFree
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY certs/*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates || true
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Python deps
COPY runner/requirements.txt /app/runner/requirements.txt
RUN pip install --no-cache-dir -r /app/runner/requirements.txt

# Code + proto
COPY runner /app/runner
COPY dsl    /app/dsl
COPY proto  /app/proto

# Generate stubs
RUN python -m grpc_tools.protoc -I./proto \
    --python_out=. --grpc_python_out=. \
    ./proto/query.proto

ENV RUNNER_MODE=real SQLITE_DB=/data/app.db LOG_LEVEL=INFO PYTHONPATH=/app
EXPOSE 50051
CMD ["python", "runner/runner_server.py"]
