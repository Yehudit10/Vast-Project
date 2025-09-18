# FROM python:3.11-slim
# ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# WORKDIR /app

# # # System CA + NetFree
# # RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
# # COPY certs/*.crt /usr/local/share/ca-certificates/
# # RUN update-ca-certificates || true
# # ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
# #     REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
# #     PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# # Python deps from repo root
# COPY requirements.txt /app/requirements.txt
# RUN pip install --no-cache-dir -r /app/requirements.txt


# # Copy source under /app/vast/*
# COPY src/vast/services /app/vast/services


# # Set environment variable for DB if needed
# ENV SQLITE_DB=/data/app.db

# ENV PYTHONPATH=/app/vast/proto/generated:/app

# # Expose port if metrics serve HTTP (optional)
# EXPOSE 8001

# # Run the metrics app
# CMD ["python", "-m", "vast.services.sensors_metrics_app"]

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# התקנת ספריות מערכת חיוניות ל-PyQt6 WebEngine
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libxrender1 \
    libxext6 \
    libx11-6 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# התקנת PyQt6 ו-WebEngine עבור Linux
RUN pip install --no-cache-dir PyQt6==6.9.1 PyQt6-WebEngine==6.9.0

# Python deps from repo root
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source under /app/vast/*
COPY src/vast/services /app/vast/services

# Set environment variable for DB if needed
ENV SQLITE_DB=/data/app.db
ENV PYTHONPATH=/app/vast/proto/generated:/app

# Expose port if metrics serve HTTP (optional)
EXPOSE 8001

# Run the metrics app
CMD ["python", "-m", "vast.services.sensors_metrics_app"]
