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

ENV PIP_DEFAULT_TIMEOUT=600

# Python deps
COPY requirements.txt /app/requirements.txt
# Install all deps EXCEPT grpcio-tools (we use pre-generated stubs)
RUN grep -v '^grpcio-tools' /app/requirements.txt > /app/requirements.nogen.txt && \
    python -m pip install --upgrade pip setuptools wheel --no-cache-dir && \
    pip install --no-cache-dir --timeout 600 -r /app/requirements.nogen.txt \
      --index-url https://pypi.org/simple \
      --trusted-host pypi.org \
      --trusted-host pypi.python.org \
      --trusted-host files.pythonhosted.org \
       && pip install --no-cache-dir "grpcio>=1.74.0"

# Copy source under /app/vast/*
COPY src/vast/gateway /app/vast/gateway
COPY src/vast/proto   /app/vast/proto

ENV PYTHONPATH=/app/vast/proto/generated:/app
ENV RUNNER_ADDR=runner:50051
EXPOSE 8000
CMD ["uvicorn", "vast.gateway.gateway_main:app", "--host", "0.0.0.0", "--port", "8000"]