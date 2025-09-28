FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# build arg
ARG USE_NETFREE=true

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*

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



# # System CA + add NetFree certs
# RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
# COPY certs/*.crt /usr/local/share/ca-certificates/
# RUN update-ca-certificates || true
# ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
#     REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
#     PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# Python deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source under /app/vast/*
COPY src/vast/gateway /app/vast/gateway
COPY src/vast/proto   /app/vast/proto

# Generate stubs
RUN python -m grpc_tools.protoc -I./vast/proto \
    --python_out=. --grpc_python_out=. \
    ./vast/proto/query.proto

ENV PYTHONPATH=/app/vast/proto/generated:/app
ENV RUNNER_ADDR=runner:50051
EXPOSE 8000
CMD ["uvicorn", "vast.gateway.gateway_main:app", "--host", "0.0.0.0", "--port", "8000"]
