FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

COPY certs /app/certs

RUN apt-get update && \
    apt-get install -y ca-certificates && \
    cp /app/certs/*.crt /usr/local/share/ca-certificates/ && \
    update-ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "backend/app.py"]