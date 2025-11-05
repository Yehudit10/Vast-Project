# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Build argument
ARG USE_NETFREE=true

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

# Install NetFree certificates only if USE_NETFREE=true
RUN if [ "$USE_NETFREE" = "true" ]; then \
        echo "Configuring NetFree certificates..."; \
        # Check if the certificate file exists
        if [ -n "$(ls ./*.crt 2>/dev/null)" ]; then \
            cp ./*.crt /usr/local/share/ca-certificates/; \
            chmod 644 /usr/local/share/ca-certificates/*.crt; \
            update-ca-certificates; \
        else \
            echo "No NetFree certificate found, skipping"; \
        fi; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir \
    --trusted-host pypi.org --trusted-host files.pythonhosted.org \
    paho-mqtt boto3 requests

WORKDIR /app
COPY app.py .
COPY config.py .
ENV OUT_DIR=/out
VOLUME ["/out"]
CMD ["python","-u","/app/app.py"]
