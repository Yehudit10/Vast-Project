FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# build arg
ARG USE_NETFREE=true

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY certs /app/certs
# System CA + add NetFree certs
RUN if [ "$USE_NETFREE" = "true" ] && [ -d ./certs ] && [ "$(ls ./certs/*.crt 2>/dev/null)" ]; then \
    echo "Configuring NetFree certificates..."; \
    cp ./certs/*.crt /usr/local/share/ca-certificates/; \
    update-ca-certificates; \
    fi

# SSL certs env   
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt


# Python deps from repo root
COPY requirements.txt /app/requirements.txt
# RUN pip install --no-cache-dir -r /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel --no-cache-dir && \
    pip config set global.timeout 600 && pip config set global.retries 10 && \
    for i in 1 2 3 4 5; do \
        pip install --no-cache-dir --timeout 600 -r /app/requirements.txt && break; \
        echo "pip failed on attempt $i; retrying in $((i*5))s..."; sleep $((i*5)); \
    done

# Copy source under /app/vast/*
COPY src/vast/runner /app/vast/runner
COPY src/vast/dsl    /app/vast/dsl
COPY src/vast/proto  /app/vast/proto


# Generate stubs
RUN pip install --no-cache-dir grpcio-tools==1.62.2 && \
    pip install --no-cache-dir "protobuf==6.31.1"
RUN python -m grpc_tools.protoc -I./vast/proto \
    --python_out=. --grpc_python_out=. \
    ./vast/proto/query.proto

ENV RUNNER_MODE=real SQLITE_DB=/data/app.db LOG_LEVEL=INFO PYTHONPATH=/app
ENV PYTHONPATH=/app/vast/proto/generated:/app

EXPOSE 50051
CMD ["python", "vast/runner/runner_server.py"]