#!/bin/bash
set -e
set -x

export DISPLAY=:0
rm -f /tmp/.X0-lock

echo "[INFO] Starting Xvfb..."
Xvfb :0 -screen 0 1920x1080x24 &
sleep 3

echo "[INFO] Starting fluxbox..."
fluxbox &
sleep 1

echo "[INFO] Starting x11vnc..."
x11vnc -display :0 -nopw -forever -shared &
sleep 1

echo "[INFO] Starting noVNC..."
/opt/noVNC/utils/novnc_proxy --vnc localhost:5900 --listen ${NO_VNC_PORT:-8080} &

echo "[INFO] Starting PyQt application..."
exec python /app/src/vast/main.py

#!/usr/bin/env bash
# set -euo pipefail

# : "${MEDIA_BASE:?}"
# : "${INCIDENT:=placeholder}"
# : "${MEDIA_TOKEN:=}"
# : "${ALERTS_WS:=}"
# : "${PORT:=19090}"
# : "${BIND:=0.0.0.0}"
# : "${REFRESH_MS:=200}"
# : "${NETWORK_CACHING:=250}"

# export DISPLAY=:99
# export XAUTHORITY=/root/.Xauthority
# export QT_QPA_PLATFORM=xcb

# rm -f /tmp/.X99-lock

# # 1) Start Xvfb (no -ac now)
# Xvfb "$DISPLAY" -screen 0 1280x800x24 -nolisten tcp &
# # Wait for socket
# for i in $(seq 1 50); do
#   [ -S "/tmp/.X11-unix/X${DISPLAY#:}" ] && break
#   sleep 0.1
# done

# # 2) Create Xauthority cookie
# touch "$XAUTHORITY"
# COOKIE="$(openssl rand -hex 16)"
# xauth -f "$XAUTHORITY" add "$DISPLAY" . "$COOKIE" || true

# # 3) Start fluxbox, x11vnc, websockify
# fluxbox >/tmp/fluxbox.log 2>&1 &
# x11vnc -display "$DISPLAY" -auth "$XAUTHORITY" \
#   -forever -shared -nopw -rfbport 5900 -quiet -noxrecord -noxfixes -noxdamage &
# websockify --web=/usr/share/novnc/ 6080 localhost:5900 &

# export QTWEBENGINE_DISABLE_SANDBOX=1

# # 4) Run the app
# exec /opt/venv/bin/python /app/src/vast/main.py


# #!/usr/bin/env bash
# set -euo pipefail
# set -x

# # ------------------------------
# # 🖥️  Environment setup
# # ------------------------------
# export DISPLAY=:99
# export XAUTHORITY=/tmp/.Xauthority

# rm -f /tmp/.X99-lock /tmp/.X0-lock
# mkdir -p /tmp/.X11-unix
# chmod 1777 /tmp/.X11-unix

# # ------------------------------
# # 🧠  Start Xvfb (virtual X server)
# # ------------------------------
# echo "[INFO] Starting Xvfb on $DISPLAY..."
# Xvfb "$DISPLAY" -screen 0 1920x1080x24 -nolisten tcp &
# # Wait until Xvfb socket is ready
# for i in $(seq 1 50); do
#   [ -S "/tmp/.X11-unix/X${DISPLAY#:}" ] && break
#   sleep 0.1
# done

# # ------------------------------
# # 🔐  Create Xauthority cookie
# # ------------------------------
# echo "[INFO] Creating Xauthority cookie..."
# touch "$XAUTHORITY"
# COOKIE="$(openssl rand -hex 16)"
# xauth -f "$XAUTHORITY" add "$DISPLAY" . "$COOKIE" || true

# # ------------------------------
# # 🪟  Start lightweight window manager (Fluxbox)
# # ------------------------------
# echo "[INFO] Starting fluxbox..."
# fluxbox >/tmp/fluxbox.log 2>&1 &
# sleep 1

# # ------------------------------
# # 🧩  Start x11vnc (VNC bridge)
# # ------------------------------
# echo "[INFO] Starting x11vnc..."
# x11vnc -display "$DISPLAY" -auth "$XAUTHORITY" \
#   -forever -shared -nopw \
#   -rfbport 5900 -quiet -noxrecord -noxfixes -noxdamage &
# sleep 1

# # ------------------------------
# # 🌐  Start noVNC (WebSocket bridge)
# # ------------------------------
# NOVNC_PORT=${NO_VNC_PORT:-6080}
# echo "[INFO] Starting noVNC on port $NOVNC_PORT..."
# /opt/noVNC/utils/novnc_proxy --vnc localhost:5900 --listen "$NOVNC_PORT" &
# sleep 1

# # ------------------------------
# # 🧰  Diagnostics
# # ------------------------------
# echo "[INFO] DISPLAY=$DISPLAY"
# echo "[INFO] Xvfb socket ready? $(ls /tmp/.X11-unix)"
# echo "[INFO] Launching PyQt6 application..."

# # ------------------------------
# # 🚀  Launch the main PyQt application
# # ------------------------------
# exec /opt/venv/bin/python /app/src/vast/main.py
