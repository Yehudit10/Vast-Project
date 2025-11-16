# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt

RUN chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt && update-ca-certificates

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY analyze_sensors.py ./
COPY profiles_runtime.py ./        

COPY app.py ./
COPY data/ ./data/
COPY zones.geojson ./
RUN mkdir -p /app/reports/plots


EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

