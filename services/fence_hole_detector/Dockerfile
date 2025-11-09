# Base image
FROM python:3.11-slim

# System deps for OpenCV wheels + SSL + curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Trust store (optional org CAs)
WORKDIR /app
COPY certs/ /app/certs/
RUN if ls /app/certs/*.crt >/dev/null 2>&1; then \
      cp /app/certs/*.crt /usr/local/share/ca-certificates/ && update-ca-certificates; \
    else \
      echo "No custom CA certs found, skipping."; \
    fi
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

# Install Python deps early for better layer caching
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Copy service sources into a package path: /app/services/fence_hole_detector
# This preserves the import path 'services.fence_hole_detector.*'
COPY . /app/services/fence_hole_detector

# Ensure these are packages (PEP420 usually ok, but we make it explicit)
RUN mkdir -p /app/services && \
    touch /app/services/__init__.py && \
    touch /app/services/fence_hole_detector/__init__.py

# Make sure Python can import from /app
ENV PYTHONPATH=/app

EXPOSE 8088

# Run FastAPI app (module path)
CMD ["uvicorn", "services.fence_hole_detector.app:app", \
     "--host", "0.0.0.0", "--port", "8088", "--log-level", "info"]
