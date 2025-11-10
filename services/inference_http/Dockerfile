#FROM python:3.11-slim
#ENV PIP_NO_CACHE_DIR=1 \
#    PIP_DEFAULT_TIMEOUT=1200 \
#    PIP_DISABLE_PIP_VERSION_CHECK=1
#
#WORKDIR /app
#
## Copy certs dir (may be empty) and trust *.crt if present
##COPY certs/ /tmp/certs/
#RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && \
#    rm -rf /var/lib/apt/lists/* && \
#    if [ -d /tmp/certs ] && ls /tmp/certs/*.crt >/dev/null 2>&1; then \
#      cp /tmp/certs/*.crt /usr/local/share/ca-certificates/ && \
#      chmod 644 /usr/local/share/ca-certificates/*.crt && \
#      update-ca-certificates; \
#    else \
#      echo "No extra CA certs found. Skipping CA update."; \
#    fi
#    
#ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
#    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
#    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
#    PIP_CERT=/etc/ssl/certs/ca-certificates.crt
#RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf
#
## Python deps
#RUN python -m pip install --upgrade pip setuptools wheel certifi && \
#    pip install --no-cache-dir numpy==1.26.4 --only-binary=:all:
#
#RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
#    torch==2.1.2 torchvision==0.16.2 --only-binary=:all: --upgrade-strategy only-if-needed
#
#COPY requirements.txt /app/requirements.txt
#RUN pip install --no-cache-dir -r /app/requirements.txt --only-binary=:all: --upgrade-strategy only-if-needed
#
#COPY app.py model_registry.py /app/
#COPY adapters /app/adapters
#COPY models   /app/models
#
#EXPOSE 8000
#CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

# ============================================================
# Unified Inference HTTP Dockerfile (Fruit + Camera + YOLO)
# ============================================================

# בסיס קל משקל
FROM python:3.11-slim


# הגדרות ברירת מחדל של pip
ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=1200

# ספריית עבודה
WORKDIR /app

# ------------------------------------------------------------
# שלב 1: התקנת תלויות מערכת (ל־OpenCV, Torch, Numpy וכו’)
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libglib2.0-dev \
    libsm6 \
    libxrender1 \
    libxext6 \
    libgl1 \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# ------------------------------------------------------------
# שלב 2: עדכון כלי pip והתקנת NumPy ו־Torch
# ------------------------------------------------------------
RUN python -m pip install --upgrade pip setuptools wheel --only-binary=:all: && \
    pip install --no-cache-dir numpy==1.26.4 --only-binary=:all: && \
    pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==2.1.2 torchvision==0.16.2 --only-binary=:all: --upgrade-strategy only-if-needed

# ------------------------------------------------------------
# שלב 3: העתקת קובץ הדרישות והתקנת שאר הספריות
# ------------------------------------------------------------

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=1200 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy certs dir (may be empty) and trust *.crt if present
# COPY certs/ /tmp/certs/
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/* && \
    if [ -d /tmp/certs ] && ls /tmp/certs/*.crt >/dev/null 2>&1; then \
    cp /tmp/certs/*.crt /usr/local/share/ca-certificates/ && \
    chmod 644 /usr/local/share/ca-certificates/*.crt && \
    update-ca-certificates; \
    else \
    echo "No extra CA certs found. Skipping CA update."; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    CURL_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt
RUN printf "[global]\ncert = /etc/ssl/certs/ca-certificates.crt\n" > /etc/pip.conf

# Python deps
RUN python -m pip install --upgrade pip setuptools wheel certifi && \
    pip install --no-cache-dir numpy==1.26.4 --only-binary=:all:

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    torch==2.1.2 torchvision==0.16.2 --only-binary=:all: --upgrade-strategy only-if-needed

COPY requirements.txt /app/requirements.txt


# נוסיף כאן את כל הספריות שצריכות להיות בכל מודל:
# boto3, ultralytics, opencv, pillow, requests וכו’
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir \
        opencv-python-headless \
        ultralytics==8.2.34 \
        boto3 \
        pillow \
        requests \
        "numpy<2" \
        && rm -rf /root/.cache/pip

# ------------------------------------------------------------
# שלב 4: העתקת קוד המקור של השירות
# ------------------------------------------------------------

COPY app.py model_registry.py /app/
COPY adapters /app/adapters
COPY models /app/models
COPY weights /app/weights


# ------------------------------------------------------------
# שלב 5: חשיפת פורט ופקודת ברירת מחדל
# ------------------------------------------------------------
EXPOSE 8004

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8004"]
