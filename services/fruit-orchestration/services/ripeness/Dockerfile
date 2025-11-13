FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates openssl libpq-dev build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY certs/ /usr/local/share/ca-certificates/
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
    files.pythonhosted.org\n\
    download.pytorch.org\n" > /etc/pip.conf

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

COPY requirements.txt /app/
RUN pip install --no-cache-dir --timeout 120 --index-url https://download.pytorch.org/whl/cpu \
    --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org \
      torch==2.3.1 torchvision==0.18.1 \
 && pip install --no-cache-dir -r /app/requirements.txt \
 && pip install --no-cache-dir fastapi "uvicorn[standard]"
COPY api/ /app/api/
COPY model/ /app/model
COPY jobs/ /app/jobs/
COPY configs/ /app/configs/
# Create models directory and copy model file
RUN mkdir -p /app/models
COPY checkpoints/mobilenet_v3_large/best_conditional.pt /app/models/best_conditional.pt

# Create __init__.py files for Python modules
RUN touch /app/model/__init__.py \
    && touch /app/model/architecture/__init__.py \
    && touch /app/model/data/__init__.py \
    && touch /app/jobs/__init__.py \
    && touch /app/api/__init__.py

ENV PYTHONPATH=/app

EXPOSE 8088
ENV MODEL_PATH=/app/models/best_conditional.pt \
    MODEL_NAME=best_conditional \
    BATCH_LIMIT=500

CMD ["uvicorn", "api.ripeness_api:app", "--host", "0.0.0.0", "--port", "8088", "--reload"]
