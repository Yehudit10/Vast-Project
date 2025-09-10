# syntax=docker/dockerfile:1
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*


# COPY netfree-ca.crt /usr/local/share/ca-certificates/netfree-ca.crt
# RUN chmod 644 /usr/local/share/ca-certificates/netfree-ca.crt && update-ca-certificates

# ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
# ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
# ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir \
    --trusted-host pypi.org --trusted-host files.pythonhosted.org \
    paho-mqtt boto3 requests

WORKDIR /app
COPY app.py .
COPY config.py .
ENV OUT_DIR=/out
VOLUME ["/out"]
CMD ["python","-u","/app/app.py"]
