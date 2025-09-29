FROM python:3.11-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# ספריות מערכת בסיסיות (opencv צריך libgl1)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# 1) מעתיקים את ה-CA הארגוני (למשל netfree-ca.crt) ומעדכנים את store
COPY deploy/certs/ /usr/local/share/ca-certificates/
RUN update-ca-certificates || true

# 2) מכריחים את pip/requests להשתמש ב-CA של המערכת
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
# (וגם קובץ קונפיג ל-pip)
RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

# 3) מתקינים תלויות
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# קוד ו-SQL
COPY src/        /app/src/
COPY deploy/sql/ /app/deploy/sql/

CMD ["python","-u","/app/src/main.py"]