FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
# RUN chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt && update-ca-certificates

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir \
  --trusted-host pypi.org --trusted-host files.pythonhosted.org \
  -r requirements.txt

COPY app ./app

ENTRYPOINT ["python", "-m", "app.tools.generate_contracts"]
