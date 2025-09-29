FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY deploy/certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates || true

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY src/        /app/src/
COPY deploy/sql/ /app/deploy/sql/

CMD ["python","-u","/app/src/main.py"]