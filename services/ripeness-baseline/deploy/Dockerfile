FROM python:3.11-slim

WORKDIR /app

# 1) תעודות CA, כלים מינימליים, ספריות ל-OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates build-essential libgl1 curl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 2) (אופציונלי) העברת פרוקסי בזמן build
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV http_proxy=${HTTP_PROXY} https_proxy=${HTTPS_PROXY}

# 3) הוספת תעודת ה-Root הארגונית (אם קיימת)
#    אם אין קובץ כזה - השורות האלו לא יפעלו (אבל זה בסדר)
COPY deploy/certs/corp-root.crt /usr/local/share/ca-certificates/corp-root.crt
RUN if [ -f /usr/local/share/ca-certificates/corp-root.crt ]; then update-ca-certificates; fi

# 4) תלות פייתון (נשתמש ב--trusted-host כדי לרכך בדיקות SSL מחמירות)
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
 && pip install --no-cache-dir -r requirements.txt \
      --trusted-host pypi.org --trusted-host files.pythonhosted.org

# 5) קוד + SQL + דוגמאות
COPY src/ ./src/
COPY deploy/sql/ ./deploy/sql/
COPY samples/ ./samples/

ENV PYTHONPATH=/app/src
ENV SAMPLES_DIR=/app/samples
ENV FRUIT_TYPE=apple

CMD ["python","-u","/app/src/main.py"]
