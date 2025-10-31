# FROM ubuntu:24.04

# ENV DEBIAN_FRONTEND=noninteractive \
#     LANG=C.UTF-8 \
#     LC_ALL=C.UTF-8 \
#     QT_QPA_PLATFORM=xcb \
#     PYTHONUNBUFFERED=1 \
#     DISPLAY=:99 \
#     NO_VNC_PORT=6080

# # ----------------------------------------------------------------------
# # 🧩 System dependencies (GUI, VNC, PyQt6, VLC, etc.)
# # ----------------------------------------------------------------------
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     # 🧩 Core Python & tools
#     python3 python3-pip python3-venv \
#     procps iproute2 net-tools git wget curl openssl ca-certificates xz-utils xauth python3-tk \
#     gosu vlc \
#     \
#     # 🖥️ Virtual desktop stack (VNC + Xvfb + window manager)
#     xvfb x11vnc fluxbox novnc websockify \
#     \
#     # 🧱 Core X11 / OpenGL / EGL deps for Qt
#     libgl1 libegl1 libx11-6 libxcomposite1 libxext6 libxi6 libxtst6 libsm6 \
#     libxkbcommon0 libxkbcommon-x11-0 libxkbfile1 libxrender1 libxrandr2 \
#     libxfixes3 libxdamage1 libwayland-cursor0 libwayland-egl1 \
#     \
#     # ✅ Critical Qt 6.5+ X11 runtime deps
#     libxcb-cursor0 libxcb-icccm4 libxcb-util1 libxcb-image0 \
#     libxcb-keysyms1 libxcb-render0 libxcb-render-util0 libxcb-shape0 \
#     libxcb-xkb1 libxcb-xinerama0 \
#     \
#     # 🧩 Font, text & theme rendering
#     libfontconfig1 libfreetype6 libpango-1.0-0 libharfbuzz0b \
#     \
#     # 🧠 Accessibility / sound / security libs
#     libatk1.0-0 libatk-bridge2.0-0 libnss3 libnspr4 \
#     libdbus-1-3 libkrb5-3 libgssapi-krb5-2 libasound2t64 libpulse0 libatomic1 \
#     \
#     # 🌈 Qt6 & GTK3 integration (Adwaita theme)
#     qt6-base-dev qt6-gtk-platformtheme qt6-wayland qt6-qpa-plugins \
#     libgtk-3-0 libgdk-pixbuf-2.0-0 libgobject-2.0-0 libglib2.0-0 libcanberra-gtk3-0 \
#     adwaita-icon-theme \
#     \
#     # 🧾 Font and GTK runtime config
#     fonts-dejavu fonts-liberation fonts-freefont-ttf fontconfig-config \
#     hicolor-icon-theme shared-mime-info gsettings-desktop-schemas \
#  && rm -rf /var/lib/apt/lists/*




#  && rm -rf /var/lib/apt/lists/*

# # ----------------------------------------------------------------------
# # ✅ Ensure fontconfig has a config file (fixes "Cannot load default config file")
# # ----------------------------------------------------------------------
# RUN mkdir -p /etc/fonts && \
#     if [ ! -f /etc/fonts/fonts.conf ]; then \
#         echo '<?xml version="1.0"?>\
# <!DOCTYPE fontconfig SYSTEM "fonts.dtd">\
# <fontconfig>\
#  <dir>/usr/share/fonts</dir>\
#  <config></config>\
# </fontconfig>' > /etc/fonts/fonts.conf; \
#     fi

# # ----------------------------------------------------------------------
# # 🧰 noVNC setup
# # ----------------------------------------------------------------------
# RUN mkdir -p /opt && \
#     wget --tries=3 --timeout=30 -O /tmp/novnc.tar.gz https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz && \
#     tar xzf /tmp/novnc.tar.gz -C /opt && \
#     mv /opt/noVNC-1.4.0 /opt/noVNC && \
#     rm /tmp/novnc.tar.gz && \
#     git clone --depth 1 https://github.com/novnc/websockify /opt/noVNC/utils/websockify

# # ----------------------------------------------------------------------
# # 🧱 Python virtual environment + dependencies
# # ----------------------------------------------------------------------
# WORKDIR /app
# COPY requirements.txt /app/requirements.txt
# RUN python3 -m venv /opt/venv \
#  && . /opt/venv/bin/activate \
#  && pip install --no-cache-dir -r /app/requirements.txt


# # ----------------------------------------------------------------------
# # 🌈 Qt / GTK3 environment
# # ----------------------------------------------------------------------
# # ----------------------------------------------------------------------
# # 🌈 Qt / GTK3 environment + style fixes
# # ----------------------------------------------------------------------
# # ----------------------------------------------------------------------
# # 🌈 Qt / GTK3 environment — GTK theme fix
# # ----------------------------------------------------------------------
# ENV PATH="/opt/venv/bin:${PATH}" \
#     QT_PLUGIN_PATH="/opt/venv/lib/python3.12/site-packages/PyQt6/Qt6/plugins:/usr/lib/x86_64-linux-gnu/qt6/plugins" \
#     QT_QPA_PLATFORMTHEME=gtk3 \
#     QT_QPA_PLATFORM=xcb \
#     XDG_RUNTIME_DIR=/tmp/xdg \
#     XDG_DATA_DIRS="/usr/share:/usr/local/share" \
#     XDG_CONFIG_DIRS="/etc/xdg" \
#     GTK_THEME=Adwaita:dark \
#     GDK_BACKEND=x11 \
#     NO_AT_BRIDGE=1


# RUN mkdir -p /tmp/xdg /usr/share/icons/hicolor && update-icon-caches /usr/share/icons/hicolor || true



# # ----------------------------------------------------------------------
# # 🧩 Application code
# # ----------------------------------------------------------------------
# COPY src/vast /app/src/vast
# COPY src/vast/desktop/start.sh /app/start.sh
# RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# # Ensure directories are accessible
# RUN mkdir -p /app/secrets /tmp/.X11-unix && chmod -R 777 /app/secrets /tmp

# # ----------------------------------------------------------------------
# # 👤 Non-root user
# # ----------------------------------------------------------------------
# RUN useradd -m -s /bin/bash appuser && chown -R appuser:appuser /app /opt /tmp
# USER appuser

# # ----------------------------------------------------------------------
# # 🌐 Ports & environment
# # ----------------------------------------------------------------------
# EXPOSE 5900 6080
# ENV PYTHONPATH=/app/src:/app

# # ----------------------------------------------------------------------
# # 🚀 Default entrypoint
# # ----------------------------------------------------------------------
# CMD ["/app/start.sh"]

# FROM ubuntu:24.04

# ENV DEBIAN_FRONTEND=noninteractive \
#     DISPLAY=:99 \
#     LANG=C.UTF-8 \
#     LC_ALL=C.UTF-8 \
#     QT_QPA_PLATFORM=xcb \
#     PYTHONUNBUFFERED=1


# RUN apt-get update && apt-get install -y --no-install-recommends \
#   python3 python3-pip python3-venv \
#   xvfb x11vnc fluxbox novnc websockify vlc \
#   ca-certificates curl wget xz-utils openssl xauth \
#   libgl1 libegl1 libx11-6 libxcomposite1 libxext6 libxi6 libxtst6 libsm6 \
#   libxkbcommon0 libxkbcommon-x11-0 libxkbfile1 libxrender1 libxrandr2 \
#   libxfixes3 libxdamage1 libwayland-cursor0 libwayland-egl1 \
#   libnss3 libnspr4 libdbus-1-3 libatomic1 xkb-data \
#   libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
#   libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libxcb-util1 \
#   fonts-dejavu-core libfontconfig1 libfreetype6 \
#   && rm -rf /var/lib/apt/lists/*



# # App
# WORKDIR /app
# COPY requirements.txt /app/requirements.txt


# # Virtualenv (avoid PEP 668 issues) + install wheels
# RUN python3 -m venv /opt/venv \
#  && . /opt/venv/bin/activate \
#  && pip install --no-cache-dir -r /app/requirements.txt

# # Use venv by default
# ENV PATH="/opt/venv/bin:${PATH}"

# # Startup script
# COPY src/vast /app/src/vast
# COPY src/vast/desktop/start.sh /app/start.sh
# RUN chmod +x /app/start.sh

# EXPOSE 5900 6080
# ENV PYTHONPATH=/app/src:/app
# CMD ["/app/start.sh"]


# FROM python:3.11-slim

# # ───────────────────────────────────────────────
# #   Base environment
# # ───────────────────────────────────────────────
# ENV DEBIAN_FRONTEND=noninteractive \
#     PYTHONDONTWRITEBYTECODE=1 \
#     PYTHONUNBUFFERED=1 \
#     DISPLAY=:99 \
#     LANG=C.UTF-8 \
#     LC_ALL=C.UTF-8 \
#     QT_QPA_PLATFORM=xcb

# WORKDIR /app

# # ───────────────────────────────────────────────
# #   System dependencies (X11, PyQt6, VLC, VNC, etc.)
# # ───────────────────────────────────────────────
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     # GUI / VNC
#     xvfb x11vnc fluxbox novnc websockify \
#     # Graphics and X11 dependencies for PyQt6 / OpenCV / VLC
#     libgl1 libegl1 libx11-6 libxcomposite1 libxext6 libxi6 libxtst6 libsm6 \
#     libxkbcommon0 libxkbcommon-x11-0 libxkbfile1 libxrender1 libxrandr2 \
#     libxfixes3 libxdamage1 libwayland-cursor0 libwayland-egl1 libxcb-cursor0 \
#     libxcb-icccm4 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render0 \
#     libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libfontconfig1 libfreetype6 \
#     libpango-1.0-0 libharfbuzz0b libatk1.0-0 libatk-bridge2.0-0 libnss3 \
#     libnspr4 libdbus-1-3 libkrb5-3 libgssapi-krb5-2 libasound2 libpulse0 \
#     libxcb-xinerama0 libxcb-randr0 \
#     # Utilities
#     git wget curl ca-certificates xauth net-tools procps iproute2 gosu \
#     # VLC player
#     vlc \
#     # Python GUI helper
#     python3-tk \
#  && rm -rf /var/lib/apt/lists/*

# # ───────────────────────────────────────────────
# #   Certificates
# # ───────────────────────────────────────────────
# # COPY certs /app/certs
# # RUN if [ -d ./certs ] && [ "$(ls ./certs/*.crt 2>/dev/null)" ]; then \
# #         echo "Installing custom certificates..."; \
# #         cp ./certs/*.crt /usr/local/share/ca-certificates/; \
# #         update-ca-certificates; \
# #     fi
# ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
# ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
# ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# # ───────────────────────────────────────────────
# #   Install Python dependencies (virtualenv)
# # ───────────────────────────────────────────────
# COPY requirements.txt /app/requirements.txt
# RUN python -m venv /opt/venv && \
#     . /opt/venv/bin/activate && \
#     pip install --no-cache-dir -r /app/requirements.txt
# ENV PATH="/opt/venv/bin:${PATH}"

# # ───────────────────────────────────────────────
# #   noVNC setup (custom manual installation)
# # ───────────────────────────────────────────────
# RUN mkdir -p /opt && \
#     wget --tries=3 --timeout=30 -O /tmp/novnc.tar.gz https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz && \
#     tar xzf /tmp/novnc.tar.gz -C /opt && \
#     mv /opt/noVNC-1.4.0 /opt/noVNC && \
#     rm /tmp/novnc.tar.gz && \
#     git clone --depth 1 https://github.com/novnc/websockify /opt/noVNC/utils/websockify

# # ───────────────────────────────────────────────
# #   Application code
# # ───────────────────────────────────────────────
# COPY src/vast /app/src/vast
# COPY src/vast/desktop/start.sh /app/start.sh
# RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh

# # ───────────────────────────────────────────────
# #   User and permissions
# # ───────────────────────────────────────────────
# RUN useradd -m -s /bin/bash appuser \
#     && mkdir -p /app/secrets /tmp/.X11-unix \
#     && chmod -R 777 /app/secrets /tmp /opt/noVNC /var/tmp \
#     && chown -R appuser:appuser /app /opt/noVNC /tmp /var/tmp
# USER appuser

# # ───────────────────────────────────────────────
# #   Ports and runtime environment
# # ───────────────────────────────────────────────
# EXPOSE 5900 6080
# ENV PYTHONPATH=/app/src:/app \
#     NO_VNC_PORT=6080

# CMD ["/app/start.sh"]



FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# ───────── system dependencies ─────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libegl1 libx11-6 libxcomposite1 libxext6 libxi6 libxtst6 libsm6 \
    libxkbcommon0 libxkbcommon-x11-0 libxkbfile1 libxrender1 libxrandr2 \
    libxfixes3 libxdamage1 libwayland-cursor0 libwayland-egl1 libxcb-cursor0 \
    libxcb-icccm4 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render0 \
    libxcb-render-util0 libxcb-shape0 libxcb-xkb1 libfontconfig1 libfreetype6 \
    libpango-1.0-0 libharfbuzz0b libatk1.0-0 libatk-bridge2.0-0 libnss3 \
    libnspr4 libdbus-1-3 libkrb5-3 libgssapi-krb5-2 libasound2 libpulse0 \
    fluxbox x11vnc xvfb wget net-tools python3-tk ca-certificates \
    procps iproute2 xauth git vlc libvlc5 libvlccore9 \
    fonts-dejavu-core fonts-noto-core fonts-noto-color-emoji
    && rm -rf /var/lib/apt/lists/*

# (optional) minimal extra XCB deps for PyQt
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxcb-xinerama0 libxcb-cursor0 libxcb-keysyms1 libxcb-render-util0 \
    libxcb-randr0 && rm -rf /var/lib/apt/lists/*

# # ───────── optional CA certs ─────────
# COPY certs /app/certs
# RUN if [ -d ./certs ] && [ "$(ls ./certs/*.crt 2>/dev/null)" ]; then \
#         echo "Configuring NetFree certificates..."; \
#         cp ./certs/*.crt /usr/local/share/ca-certificates/; \
#         update-ca-certificates; \
#     fi

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

# ───────── noVNC for remote GUI ─────────
RUN mkdir -p /opt && \
    wget --tries=3 --timeout=30 -O /tmp/novnc.tar.gz https://github.com/novnc/noVNC/archive/refs/tags/v1.4.0.tar.gz && \
    tar xzf /tmp/novnc.tar.gz -C /opt && \
    mv /opt/noVNC-1.4.0 /opt/noVNC && \
    rm /tmp/novnc.tar.gz && \
    git clone --depth 1 https://github.com/novnc/websockify /opt/noVNC/utils/websockify

# ───────── Python deps ─────────
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# aiohttp, python-vlc, PyQt6, and requests must be in requirements.txt
# Example (add if missing):
# PyQt6
# python-vlc
# aiohttp

# ───────── app setup ─────────
RUN useradd -m -s /bin/bash appuser \
    && mkdir -p /app /tmp/.X11-unix \
    && chown -R appuser:appuser /app /tmp /opt/noVNC /var/tmp

RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

COPY src/vast /app/src/vast
COPY src/vast/desktop/start.sh /app/start.sh
RUN sed -i 's/\r$//' /app/start.sh && chmod +x /app/start.sh && chown -R appuser:appuser /app

RUN mkdir -p /app/secrets && chmod -R 777 /app/secrets

USER appuser
EXPOSE 5900 6080   
ENV PYTHONPATH=/app/src:/app
ENV DISPLAY=:0
ENV NO_VNC_PORT=6080
ENV PORT=19100
ENV MEDIA_BASE=http://media-proxy:8080

CMD ["/app/start.sh"]




