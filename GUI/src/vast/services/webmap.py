# services/webmap.py
from __future__ import annotations
import os
import uuid
from pathlib import Path
from typing import Any

import requests
from flask import Blueprint, send_from_directory, Response, jsonify

webmap_bp = Blueprint("webmap", __name__)

TILES_ROOT = Path(__file__).resolve().parents[1] / "orthophoto_canvas" / "data" / "tiles"
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:9001")

@webmap_bp.get("/tiles/<int:z>/<int:x>/<path:y_png>")
def tiles(z: int, x: int, y_png: str):
    p = TILES_ROOT / str(z) / str(x) / y_png
    if p.is_file():
        return send_from_directory(p.parent, p.name, mimetype="image/png")
    try:
        y = int(y_png.replace(".png", ""))
        y_tms = (1 << z) - 1 - y
        p2 = TILES_ROOT / str(z) / str(x) / f"{y_tms}.png"
        if p2.is_file():
            return send_from_directory(p2.parent, p2.name, mimetype="image/png")
    except Exception:
        pass
    return Response("Tile not found", status=404)

@webmap_bp.get("/api/sensors")
def api_sensors():
    plan = {
        "source": "sensors",
        "_ops": [
            {"op": "select", "columns": [
                "sensor_id", "lat", "lon", "status", "name", "label", "battery", "moisture"
            ]},
            {"op": "where", "cond": {"any": [
                {"op": "=", "left": {"col": "status"}, "right": {"literal": "ok"}},
                {"op": "=", "left": {"col": "status"}, "right": {"literal": "warning"}}
            ]}}
        ]
    }
    headers = {"Content-Type": "application/json", "X-Request-Id": str(uuid.uuid4())}
    try:
        r = requests.post(f"{GATEWAY_URL.rstrip('/')}/runQuery", json=plan, headers=headers, timeout=20)
        r.raise_for_status()
        data: Any = r.json()
    except Exception as e:
        print(f"[webmap] ERROR fetching sensors from gateway: {e}")
        data = []

    if isinstance(data, dict):
        data = data.get("sensors", [])
    if not isinstance(data, list):
        data = []
    return jsonify(data)

@webmap_bp.get("/map")
def map_page():
    html = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Orthophoto Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.css"/>
  <style>
    html,body,#map { height: 100%; margin: 0; }
    .toolbar { position: absolute; top: 8px; left: 8px; z-index: 1000; background: #fff; padding: 6px 8px; border-radius: 6px; box-shadow: 0 1px 5px rgba(0,0,0,0.65); }
    .coords { position: absolute; bottom: 6px; right: 8px; background: rgba(255,255,255,0.85); padding: 4px 6px; border-radius: 4px; font: 12px sans-serif; }
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="toolbar">
    <label>Opacity <input id="opacity" type="range" min="0" max="1" value="1" step="0.05"></label>
  </div>
  <div class="coords" id="coords">Lat, Lon</div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.js"></script>
  <script>
    const HOME = { center: [31.895, 34.850], zoom: 15 };
    const map = L.map('map', { zoomControl: true }).setView(HOME.center, HOME.zoom);
    L.control.fullscreen().addTo(map);
    L.control.scale().addTo(map);

    const ortho = L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19, minZoom: 0, updateWhenIdle: true });
    ortho.addTo(map);

    document.getElementById('opacity').addEventListener('input', (ev) => {
      ortho.setOpacity(parseFloat(ev.target.value));
    });

    map.on('mousemove', (e) => {
      document.getElementById('coords').textContent =
        `${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`;
    });

    fetch('/api/sensors').then(r => r.json()).then(rows => {
      rows.forEach(s => {
        const lat = Number(s.lat), lon = Number(s.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
        const status = (s.status || '').toLowerCase();
        const color =
          status === 'ok' ? '#2ecc71' :
          status === 'warning' ? '#f39c12' :
          status === 'error' ? '#e74c3c' : '#2980b9';
        const m = L.circleMarker([lat, lon], { radius: 6, color, weight: 2, fillOpacity: 0.9 }).addTo(map);
        const label = s.label || s.name || s.sensor_id || '';
        const bat = s.battery != null ? `Battery: ${s.battery}` : '';
        const moi = s.moisture != null ? `Moisture: ${s.moisture}` : '';
        m.bindTooltip(`<b>${label}</b><br/>${bat}<br/>${moi}`, { direction: 'top', opacity: 0.9 });
      });
    }).catch(err => console.error('Failed to load sensors:', err));
  </script>
</body>
</html>
    """.strip()
    return Response(html, mimetype="text/html")
