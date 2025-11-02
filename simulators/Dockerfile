# Use official Python slim image
FROM python:3.12-slim

# Copy the NetFree certificate into the container
COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt

# Install system dependencies, add the certificate, and clean cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    update-ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir paho-mqtt

# Set working directory
WORKDIR /app

# Copy project files
COPY data_publisher.py .

# Run the Python script
CMD ["python", "-u", "/app/data_publisher.py"]
