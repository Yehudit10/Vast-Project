FROM python:3.11-slim

# מתקין תעודות מערכת
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# מוסיף את תעודת נטפרי/הפרוקסי
COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN update-ca-certificates

# אומר ל־pip ול-Python להשתמש בתעודה הזו
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "app.py"]
