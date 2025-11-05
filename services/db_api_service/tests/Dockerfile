FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates build-essential gcc curl && \
    rm -rf /var/lib/apt/lists/*

COPY *.crt /usr/local/share/ca-certificates/
RUN chmod 644 /usr/local/share/ca-certificates/ && update-ca-certificates

RUN python -m pip install --no-cache-dir --upgrade pip certifi
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_DEFAULT_TIMEOUT=120

COPY . /app
ENV PYTHONPATH=/app

RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir pytest httpx

ENV ENV=dev
ENV DB_DRY_RUN=1
ENV DRY_RUN_SPOOL=/tmp/api_spool
ENV DB_DSN=sqlite+pysqlite:///:memory:
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["pytest", "-q", "tests"]
