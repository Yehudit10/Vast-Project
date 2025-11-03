FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps + CA (כמו שעבד לך)
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates openssl libpq-dev build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY certs/ /usr/local/share/ca-certificates/
RUN set -eux; \
    for f in /usr/local/share/ca-certificates/*.cer; do \
      [ -f "$f" ] && openssl x509 -inform der -in "$f" -out "${f%.cer}.crt" && rm -f "$f" || true; \
    done; \
    update-ca-certificates

# pip cfg לטובת NetFree
RUN printf "[global]\n\
cert = /etc/ssl/certs/ca-certificates.crt\n\
index-url = https://pypi.org/simple\n\
trusted-host =\n\
    pypi.org\n\
    files.pythonhosted.org\n\
    download.pytorch.org\n" > /etc/pip.conf

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# התקנות: קודם Torch מהאינדקס הרשמי של CPU, אח"כ שאר החבילות
COPY requirements.txt /app/
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
      torch==2.3.1 torchvision==0.18.1 \
 && pip install --no-cache-dir -r /app/requirements.txt \
 && pip install --no-cache-dir fastapi "uvicorn[standard]"

# קוד האפליקציה
COPY scripts/  /app/scripts/
COPY models/   /app/models/

# משקלי המודל לתוך /models בתוך הקונטיינר
# התאימי את שם הקובץ המדויק שיש אצלך בתיקיית checkpoints!
COPY checkpoints/mobilenet_v3_large/best_conditional.pt /models/best_conditional.pt

# לוודא ש-Python רואה את /app כ-root module
ENV PYTHONPATH=/app

EXPOSE 8088
ENV MODEL_PATH=/models/best_conditional.pt \
    MODEL_NAME=best_conditional \
    BATCH_LIMIT=500

CMD ["uvicorn", "scripts.ripeness_api:app", "--host", "0.0.0.0", "--port", "8088"]
