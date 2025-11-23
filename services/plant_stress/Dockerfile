FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Jerusalem

RUN apt-get update && apt-get install -y --no-install-recommends \
      cron tzdata ca-certificates curl libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY certs/ /usr/local/share/ca-certificates/

RUN if find /usr/local/share/ca-certificates -maxdepth 1 -type f \
       \( -name '*.crt' -o -name '*.cer' -o -name '*.pem' \) \
       -print -quit | grep -q .; then \
        echo "Installing custom certificates from /usr/local/share/ca-certificates..."; \
        update-ca-certificates; \
    else \
        echo "No custom cert files found under /usr/local/share/ca-certificates, continuing without extra certificates."; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY src /app/src
COPY models /models
ENV MODEL_DIR=/models

COPY cronjob /etc/cron.d/plant-stress-cron
COPY run_job.sh /app/run_job.sh
COPY entrypoint.sh /entrypoint.sh

RUN sed -i 's/\r$//' /etc/cron.d/plant-stress-cron /entrypoint.sh /app/run_job.sh \
 && chmod 0644 /etc/cron.d/plant-stress-cron \
 && chmod +x /entrypoint.sh /app/run_job.sh \
 && touch /var/log/cron.log

CMD ["/entrypoint.sh"]
