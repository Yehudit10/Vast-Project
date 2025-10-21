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
