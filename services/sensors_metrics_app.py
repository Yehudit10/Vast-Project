from __future__ import annotations
import random, time, threading
from datetime import datetime, timezone
from flask import Flask, Response, send_from_directory, jsonify
from pathlib import Path
from prometheus_client import CollectorRegistry, Gauge, generate_latest, CONTENT_TYPE_LATEST
# from webmap import webmap_bp
from .webmap import webmap_bp  

app = Flask(__name__)
app.register_blueprint(webmap_bp)  # routes: /map, /tiles, /api/sensors
# TILES_ROOT = Path(__file__).resolve().parents[1] / "orthophoto_canvas" / "data" / "tiles"
REG = CollectorRegistry()

SENSOR_STATUS = Gauge("sensor_status", "1=active, 0=inactive", ["sensor"], registry=REG)
SENSORS_ACTIVE_TOTAL = Gauge("sensors_active_total", "Active sensors total", registry=REG)
SENSOR_LAST_SEEN = Gauge("sensor_last_seen_timestamp_seconds", "Last seen (unix ts)", ["sensor"], registry=REG)

SENSORS = [f"sensor_{i:03d}" for i in range(1, 41)]  # 40 sensors demo

def _tick():
    while True:
        active_count = 0
        now = datetime.now(timezone.utc).timestamp()
        for s in SENSORS:
            val = 1 if random.random() < 0.8 else 0  # ~80% active
            SENSOR_STATUS.labels(sensor=s).set(val)
            if val == 1:
                active_count += 1
                SENSOR_LAST_SEEN.labels(sensor=s).set(now)
        SENSORS_ACTIVE_TOTAL.set(active_count)
        time.sleep(5)

@app.route("/metrics")
def metrics():
    return Response(generate_latest(REG), mimetype=CONTENT_TYPE_LATEST)

@app.get("/tiles/<int:z>/<int:x>/<path:y_png>")
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

@app.get("/map")
def map_page():
    html = """<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Orthophoto Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
  <style>
    html,body,#map { height: 100%; margin: 0; }
    .toolbar { position: absolute; top: 8px; left: 8px; z-index: 1000; background: #fff; padding: 6px 8px; border-radius: 6px; box-shadow: 0 1px 5px rgba(0,0,0,0.65); }
    .toolbar label { font: 12px/1.4 sans-serif; margin-right: 6px; }
    .coords { position: absolute; bottom: 6px; right: 8px; background: rgba(255,255,255,0.85); padding: 4px 6px; border-radius: 4px; font: 12px sans-serif; }
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="toolbar">
    <label>Opacity <input id="opacity" type="range" min="0" max="1" value="1" step="0.05"></label>
    <button id="home">Home</button>
  </div>
  <div class="coords" id="coords">Lat, Lon</div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.js"></script>
  <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <script>
    const HOME = { center: [31.77, 35.21], zoom: 12 };
    const map = L.map('map', { zoomControl: true }).setView(HOME.center, HOME.zoom);
    L.control.fullscreen().addTo(map);
    L.control.scale().addTo(map);

    const ortho = L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19, minZoom: 0 });
    ortho.addTo(map);

    const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{ maxZoom: 19, attribution: '&copy; OpenStreetMap' });

    const drawn = new L.FeatureGroup().addTo(map);
    new L.Control.Draw({ edit: { featureGroup: drawn }, draw: { circle: false } }).addTo(map);
    map.on(L.Draw.Event.CREATED, e => drawn.addLayer(e.layer));

    const baseLayers = { "Orthophoto": ortho, "OSM": osm };
    const overlays = { "Drawn": drawn };
    L.control.layers(baseLayers, overlays, { collapsed: false }).addTo(map);

    document.getElementById('opacity').addEventListener('input', (ev) => {
      ortho.setOpacity(parseFloat(ev.target.value));
    });

    document.getElementById('home').addEventListener('click', () => {
      map.setView(HOME.center, HOME.zoom);
    });

    map.on('mousemove', (e) => {
      document.getElementById('coords').textContent =
        `${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`;
    });
  </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")

# Optional, only if you want markers from an API:
@app.get("/api/sensors")
def api_sensors():
    return jsonify([
        {"id": "S-001", "lat": 31.778, "lon": 35.235},
        {"id": "S-002", "lat": 31.785, "lon": 35.220},
        {"id": "S-003", "lat": 31.760, "lon": 35.250},
    ])


if __name__ == "__main__":
    threading.Thread(target=_tick, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
