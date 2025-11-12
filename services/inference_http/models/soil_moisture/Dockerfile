
FROM python:3.10-slim

WORKDIR /app

# --- 1) installing ca-certificates ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

# --- 2) copying NetFree certificate and adding it to the system ---
COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
RUN chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt && \
    update-ca-certificates

# Setting to ensure the updated certificate is used
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# --- 3) System dependencies required for FastAPI etc. ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 libsm6 libxrender1 libxext6 \
 && rm -rf /var/lib/apt/lists/*

# --- 4) Installing dependencies ---
COPY requirements-api.txt .
# RUN pip install --trusted-host pypi.org --trusted-host pypi.python.org \
#     --trusted-host files.pythonhosted.org --no-cache-dir -r requirements-api.txt

RUN pip config set global.require-hashes false && \
    pip install --trusted-host pypi.org --trusted-host pypi.python.org \
    --trusted-host files.pythonhosted.org --no-cache-dir -r requirements-api.txt
# --- 5) Copying code ---
COPY src ./src
COPY configs ./configs
COPY artifacts ./artifacts
COPY src/sql/init_db.sql /initdb/init_db.sql

ENV PYTHONPATH=/app
ENV SCHEDULE_UPDATE=1
RUN pip install python-multipart

CMD ["uvicorn", "src.app.service:app", "--host", "0.0.0.0", "--port", "8000"]