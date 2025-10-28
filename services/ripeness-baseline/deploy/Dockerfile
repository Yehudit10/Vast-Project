FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates openssl libgl1 && \
    rm -rf /var/lib/apt/lists/*

COPY deploy/certs/ /usr/local/share/ca-certificates/

RUN set -eux; \
    for f in /usr/local/share/ca-certificates/*.cer; do \
      [ -f "$f" ] && openssl x509 -inform der -in "$f" -out "${f%.cer}.crt" && rm -f "$f" || true; \
    done; \
    update-ca-certificates

RUN printf "[global]\n\
cert = /etc/ssl/certs/ca-certificates.crt\n\
index-url = https://pypi.org/simple\n\
trusted-host =\n\
    pypi.org\n\
    files.pythonhosted.org\n" > /etc/pip.conf
    
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY src/        /app/src/
COPY deploy/sql/ /app/deploy/sql/

CMD ["python","-u","/app/src/main.py"]
