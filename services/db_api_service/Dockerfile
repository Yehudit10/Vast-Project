FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY *.crt /usr/local/share/ca-certificates/
RUN chmod 644 /usr/local/share/ca-certificates/ && update-ca-certificates

ENV SSL_CERT_FILE=/etc/ssl/certs/*.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/*.crt \
    PIP_CERT=/etc/ssl/certs/*.crt \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# RUN python -m pip install --no-cache-dir --upgrade pip certifi

COPY requirements.txt .
RUN pip install --no-cache-dir \
  --trusted-host pypi.org --trusted-host files.pythonhosted.org \
  -r requirements.txt

COPY app ./app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
