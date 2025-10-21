FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libegl1 libx11-6 libxcomposite1 libxext6 libxi6 libxtst6 libsm6 \
    libxkbcommon0 libxkbcommon-x11-0 libxkbfile1 libxrender1 libxrandr2 \
    libxfixes3 libxdamage1 libwayland-cursor0 libwayland-egl1 libxcb-cursor0 \
    libxcb-icccm4 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render0 \
    libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libfontconfig1 libfreetype6 \
    libpango-1.0-0 libharfbuzz0b libatk1.0-0 libatk-bridge2.0-0 libnss3 \
    libnspr4 libdbus-1-3 libkrb5-3 libgssapi-krb5-2 libasound2 libpulse0 \
    fluxbox x11vnc xvfb wget net-tools python3-tk ca-certificates \
    procps iproute2 xauth git \
    && rm -rf /var/lib/apt/lists/*
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcb-xinerama0 libxcb-cursor0 libxcb-keysyms1 libxcb-render-util0 \
    libxcb-randr0 \
    && rm -rf /var/lib/apt/lists/*

COPY certs /app/certs
RUN if [ -d ./certs ] && [ "$(ls ./certs/*.crt 2>/dev/null)" ]; then \
        echo "Configuring NetFree certificates..."; \
        cp ./certs/*.crt /usr/local/share/ca-certificates/; \
        update-ca-certificates; \
    fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

RUN mkdir -p /opt && \
    wget --tries=3 --timeout=30 -O /tmp/novnc.tar.gz https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz && \
    tar xzf /tmp/novnc.tar.gz -C /opt && \
    mv /opt/noVNC-1.4.0 /opt/noVNC && \
    rm /tmp/novnc.tar.gz && \
    git clone --depth 1 https://github.com/novnc/websockify /opt/noVNC/utils/websockify

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd -m -s /bin/bash appuser \
    && mkdir -p /app /tmp/.X11-unix \
    && chown -R appuser:appuser /app /tmp /opt/noVNC /var/tmp
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
COPY src/vast /app/src/vast
COPY src/vast/desktop/start.sh /app/start.sh
RUN sed -i 's/\r$//' /app/start.sh && \
    chmod +x /app/start.sh && \
    chown -R appuser:appuser /app
# RUN chmod +x /app/start.sh && chown -R appuser:appuser /app
RUN mkdir -p /app/secrets && chmod -R 777 /app/secrets
USER appuser
EXPOSE 5900 6080
ENV PYTHONPATH=/app/src:/app
ENV DISPLAY=:0
ENV NO_VNC_PORT=6080
CMD ["/app/start.sh"]
