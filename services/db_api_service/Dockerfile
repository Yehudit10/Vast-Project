FROM python:3.12-slim
WORKDIR /app

# Build argument
ARG USE_NETFREE=false
# Install basic packages
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && \

    rm -rf /var/lib/apt/lists/*
# Copy certificates
COPY certs /app/certs
# Install NetFree certificates
RUN if [ "$USE_NETFREE" = "true" ]; then \
        echo "Configuring NetFree certificates..."; \
        ls -la /app/certs/; \
        if [ -f /app/certs/netfree-ca.crt ]; then \
            echo "Found NetFree certificate, installing..."; \
            cp /app/certs/netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt; \
            chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt; \
            update-ca-certificates; \
            echo "Certificate installed successfully"; \
        else \
            echo "WARNING: No NetFree certificate found at /app/certs/netfree-ca.crt, continuing without it."; \
        fi; \
    fi


# SSL cert environment variables
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# Upgrade pip with trusted hosts
RUN python -m pip install --no-cache-dir --upgrade pip --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org
# Update certifi with system certificates
RUN pip install --no-cache-dir certifi --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org && \
    cat /etc/ssl/certs/ca-certificates.crt >> $(python -m certifi) && \
    echo "Updated certifi with system certificates"
COPY requirements.txt .
# add trusted hosts during package installation
RUN pip install --no-cache-dir -r requirements.txt \
    --trusted-host pypi.org \
    --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org

COPY app ./app
EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]










<<<<<<< HEAD
# Run FastAPI app with uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
=======
>>>>>>> 8930acc7679ad3b0782d15449fd4176f5a9ea2d2
