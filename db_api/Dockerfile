FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1


RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt && update-ca-certificates


ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app
COPY requirements.txt .


RUN pip install --no-cache-dir \
    --trusted-host pypi.org --trusted-host files.pythonhosted.org \
    -r requirements.txt

COPY app ./app

ENV API_TOKEN=dev-token
ENV DB_DSN=postgresql+psycopg://postgres:postgres@postgres:5432/postgres

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
