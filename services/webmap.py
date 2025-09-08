# # # services/webmap.py
# # from __future__ import annotations
# # from pathlib import Path
# # from flask import Blueprint, send_from_directory, Response, jsonify

# # # זהו אותו מודול שה־viewer משתמש בו להצגת ה־sensors האמיתיים
# # from orthophoto_canvas.ag_io.sensors_api import get_sensors

# # webmap_bp = Blueprint("webmap", __name__)

# # # מצביע ל- <project-root>/orthophoto_canvas/data/tiles
# # TILES_ROOT = Path(__file__).resolve().parents[1] / "orthophoto_canvas" / "data" / "tiles"

# # @webmap_bp.get("/tiles/<int:z>/<int:x>/<path:y_png>")
# # def tiles(z: int, x: int, y_png: str):
# #     # XYZ
# #     p = TILES_ROOT / str(z) / str(x) / y_png
# #     if p.is_file():
# #         return send_from_directory(p.parent, p.name, mimetype="image/png")
# #     # Fallback ל-TMS (היפוך Y)
# #     try:
# #         y = int(y_png.replace(".png", ""))
# #         y_tms = (1 << z) - 1 - y
# #         p2 = TILES_ROOT / str(z) / str(x) / f"{y_tms}.png"
# #         if p2.is_file():
# #             return send_from_directory(p2.parent, p2.name, mimetype="image/png")
# #     except Exception:
# #         pass
# #     return Response("Tile not found", status=404)

# # @webmap_bp.get("/api/sensors")
# # def api_sensors():
# #     # אותם נתונים כמו ב-viewer (לא דמו)
# #     rows = get_sensors()
# #     return jsonify(rows)

# # @webmap_bp.get("/map")
# # def map_page():
# #     html = """
# # <!doctype html>
# # <html>
# # <head>
# #   <meta charset="utf-8"/>
# #   <title>Orthophoto Map</title>
# #   <meta name="viewport" content="width=device-width, initial-scale=1"/>
# #   <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
# #   <link rel="stylesheet" href="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.css"/>
# #   <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
# #   <style>
# #     html,body,#map { height: 100%; margin: 0; }
# #     .toolbar { position: absolute; top: 8px; left: 8px; z-index: 1000; background: #fff; padding: 6px 8px; border-radius: 6px; box-shadow: 0 1px 5px rgba(0,0,0,0.65); }
# #     .toolbar label { font: 12px/1.4 sans-serif; margin-right: 6px; }
# #     .coords { position: absolute; bottom: 6px; right: 8px; background: rgba(255,255,255,0.85); padding: 4px 6px; border-radius: 4px; font: 12px sans-serif; }
# #   </style>
# # </head>
# # <body>
# #   <div id="map"></div>
# #   <div class="toolbar">
# #     <label>Opacity <input id="opacity" type="range" min="0" max="1" value="1" step="0.05"></label>
# #     <button id="home">Home</button>
# #   </div>
# #   <div class="coords" id="coords">Lat, Lon</div>

# #   <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
# #   <script src="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.js"></script>
# #   <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
# #   <script>
# #     const map = L.map('map', { zoomControl: true });
# #     L.control.fullscreen().addTo(map);
# #     L.control.scale().addTo(map);

# #     // שכבת אריחים מקומיים (Orthophoto)
# #     const ortho = L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19, minZoom: 0, updateWhenIdle: true });
# #     ortho.addTo(map);

# #     // שכבת בסיס אופציונלית
# #     const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{ maxZoom: 19, attribution: '&copy; OpenStreetMap' });

# #     // שכבת ציור
# #     const drawn = new L.FeatureGroup().addTo(map);
# #     new L.Control.Draw({ edit: { featureGroup: drawn }, draw: { circle: false } }).addTo(map);

# #     const baseLayers = { "Orthophoto": ortho, "OSM": osm };
# #     const overlays = { "Drawn": drawn };
# #     L.control.layers(baseLayers, overlays, { collapsed: false }).addTo(map);

# #     // שקיפות אורתופוטו
# #     document.getElementById('opacity').addEventListener('input', (ev) => {
# #       ortho.setOpacity(parseFloat(ev.target.value));
# #     });

# #     // קואורדינטות עכבר
# #     map.on('mousemove', (e) => {
# #       document.getElementById('coords').textContent =
# #         `${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`;
# #     });

# #     // טעינת sensors אמיתיים מהשרת (אותו מקור כמו ה-viewer)
# #     fetch('/api/sensors').then(r => r.json()).then(rows => {
# #       const markers = [];
# #       rows.forEach(s => {
# #         if (typeof s.lat !== 'number' || typeof s.lon !== 'number') return;

# #         // צבע לפי סטטוס כמו ב-viewer (התאימי במידת הצורך)
# #         const status = (s.status || '').toLowerCase();
# #         const color =
# #           status === 'ok' ? '#2ecc71' :
# #           status === 'warning' ? '#f39c12' :
# #           status === 'error' ? '#e74c3c' : '#3498db';

# #         const m = L.circleMarker([s.lat, s.lon], {
# #           radius: 6, weight: 2, color: '#ffffff', fillColor: color, fillOpacity: 0.95
# #         }).addTo(map);

# #         // Tooltip על hover (כמו ב-screenshot)
# #         const name = s.name || s.label || s.sensor_id || 'sensor';
# #         const battery = (s.battery != null) ? `${s.battery}` : 'n/a';
# #         const html = `
# #           <div style="font: 13px/1.2 sans-serif">
# #             <b>${name}</b> <small>${s.sensor_id ?? ''}</small><br/>
# #             <span style="color:#2ecc71">•</span> Battery: ${battery}<br/>
# #             <span style="color:#555">•</span> Status: ${status || 'n/a'}<br/>
# #           </div>
# #         `;

# #         m.bindTooltip(html, { direction: 'top', sticky: true, opacity: 0.95, className: 'sensor-tip' });
# #         markers.push(m);
# #       });

# #       // התאמת תצוגה לכל החיישנים; אם אין—מרכז/זום ברירת מחדל
# #       if (markers.length) {
# #         const group = L.featureGroup(markers);
# #         map.fitBounds(group.getBounds().pad(0.2));
# #       } else {
# #         map.setView([31.77, 35.21], 12);
# #       }
# #     }).catch(() => {
# #       map.setView([31.77, 35.21], 12); // fallback
# #     });

# #     // כפתור "Home" חוזר לתחום כל החיישנים
# #     document.getElementById('home').addEventListener('click', () => {
# #       fetch('/api/sensors').then(r => r.json()).then(rows => {
# #         const pts = rows.filter(s => typeof s.lat === 'number' && typeof s.lon === 'number')
# #                         .map(s => [s.lat, s.lon]);
# #         if (pts.length) map.fitBounds(pts, { padding: [20,20] });
# #       });
# #     });
# #   </script>
# # </body>
# # </html>
# # """
# #     return Response(html, mimetype="text/html")







# # from flask import Blueprint, jsonify

# # webmap_bp = Blueprint("webmap", __name__)

# # @webmap_bp.get("/api/sensors")
# # def api_sensors():
# #     # TODO: החליפי למקור האמיתי שלך, או טעינה מקובץ JSON אם יש.
# #     rows = [
# #         {"sensor_id": "demo-1", "lat": 31.9000, "lon": 34.8500, "label": "Demo 1", "status": "ok"},
# #         {"sensor_id": "demo-2", "lat": 31.9017, "lon": 34.8525, "label": "Demo 2", "status": "warning"},
# #         {"sensor_id": "demo-3", "lat": 31.8982, "lon": 34.8470, "label": "Demo 3", "status": "ok"},
# #     ]
# #     return jsonify(rows)





# # import os, uuid, requests
# # from flask import Blueprint, jsonify

# # webmap_bp = Blueprint("webmap", __name__)
# # GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8000")

# # @webmap_bp.get("/api/sensors")
# # def api_sensors():
# #     plan = {
# #         "source": "sensors",
# #         "_ops": [
# #             {"op": "select", "columns": ["sensor_id","lat","lon","status","name","label","battery","moisture"]},
# #             {"op": "where", "cond": {"any": [
# #                 {"op": "=", "left": {"col": "status"}, "right": {"literal": "ok"}},
# #                 {"op": "=", "left": {"col": "status"}, "right": {"literal": "warning"}}
# #             ]}}
# #         ]
# #     }
# #     headers = {"Content-Type": "application/json", "X-Request-Id": str(uuid.uuid4())}
# #     r = requests.post(f"{GATEWAY_URL}/runQuery", json=plan, headers=headers, timeout=10)
# #     r.raise_for_status()
# #     rows = r.json()
# #     return jsonify(rows)


# # services/webmap.py
# from __future__ import annotations
# import os
# import uuid
# from pathlib import Path
# from typing import Any, List

# import requests
# from flask import Blueprint, send_from_directory, Response, jsonify

# webmap_bp = Blueprint("webmap", __name__)

# # Path to <project-root>/orthophoto_canvas/data/tiles
# TILES_ROOT = Path(__file__).resolve().parents[1] / "orthophoto_canvas" / "data" / "tiles"

# # The FastAPI gateway that exposes /runQuery (NOT the Flask port)
# GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:9001")

# @webmap_bp.get("/tiles/<int:z>/<int:x>/<path:y_png>")
# def tiles(z: int, x: int, y_png: str):
#     # XYZ
#     p = TILES_ROOT / str(z) / str(x) / y_png
#     if p.is_file():
#         return send_from_directory(p.parent, p.name, mimetype="image/png")
#     # Fallback to TMS (Y inverted)
#     try:
#         y = int(y_png.replace(".png", ""))
#         y_tms = (1 << z) - 1 - y
#         p2 = TILES_ROOT / str(z) / str(x) / f"{y_tms}.png"
#         if p2.is_file():
#             return send_from_directory(p2.parent, p2.name, mimetype="image/png")
#     except Exception:
#         pass
#     return Response("Tile not found", status=404)

# @webmap_bp.get("/api/sensors")
# def api_sensors():
#     """
#     Proxy real sensors from the gateway's /runQuery.
#     This avoids recursion (Flask -> Flask) and guarantees a single source of truth.
#     """
#     plan = {
#         "source": "sensors",
#         "_ops": [
#             {"op": "select", "columns": [
#                 "sensor_id", "lat", "lon", "status", "name", "label", "battery", "moisture"
#             ]},
#             {"op": "where", "cond": {
#                 "any": [
#                     {"op": "=", "left": {"col": "status"}, "right": {"literal": "ok"}},
#                     {"op": "=", "left": {"col": "status"}, "right": {"literal": "warning"}}
#                 ]
#             }}
#         ]
#     }
#     headers = {
#         "Content-Type": "application/json",
#         "X-Request-Id": str(uuid.uuid4()),
#     }
#     try:
#         r = requests.post(f"{GATEWAY_URL.rstrip('/')}/runQuery", json=plan, headers=headers, timeout=20)
#         r.raise_for_status()
#         data: Any = r.json()
#     except Exception as e:
#         print(f"[webmap] ERROR fetching sensors from gateway: {e}")
#         data = []
#     # If the gateway returns {"sensors":[...]} or a raw list, normalize to list
#     if isinstance(data, dict):
#         data = data.get("sensors", [])
#     if not isinstance(data, list):
#         data = []
#     return jsonify(data)

# @webmap_bp.get("/map")
# def map_page():
#     html = """
# <!doctype html>
# <html>
# <head>
#   <meta charset="utf-8"/>
#   <title>Orthophoto Map</title>
#   <meta name="viewport" content="width=device-width, initial-scale=1"/>
#   <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
#   <link rel="stylesheet" href="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.css"/>
#   <style>
#     html,body,#map { height: 100%; margin: 0; }
#     .toolbar { position: absolute; top: 8px; left: 8px; z-index: 1000; background: #fff; padding: 6px 8px; border-radius: 6px; box-shadow: 0 1px 5px rgba(0,0,0,0.65); }
#     .coords { position: absolute; bottom: 6px; right: 8px; background: rgba(255,255,255,0.85); padding: 4px 6px; border-radius: 4px; font: 12px sans-serif; }
#   </style>
# </head>
# <body>
#   <div id="map"></div>
#   <div class="toolbar">
#     <label>Opacity <input id="opacity" type="range" min="0" max="1" value="1" step="0.05"></label>
#   </div>
#   <div class="coords" id="coords">Lat, Lon</div>

#   <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
#   <script src="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.js"></script>
#   <script>
#     const HOME = { center: [31.895, 34.850], zoom: 15 };
#     const map = L.map('map', { zoomControl: true }).setView(HOME.center, HOME.zoom);
#     L.control.fullscreen().addTo(map);
#     L.control.scale().addTo(map);

#     const ortho = L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19, minZoom: 0, updateWhenIdle: true });
#     ortho.addTo(map);

#     document.getElementById('opacity').addEventListener('input', (ev) => {
#       ortho.setOpacity(parseFloat(ev.target.value));
#     });

#     map.on('mousemove', (e) => {
#       document.getElementById('coords').textContent =
#         `${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`;
#     });

#     // Real sensors overlay (same backend as the PyQt viewer)
#     fetch('/api/sensors').then(r => r.json()).then(rows => {
#       rows.forEach(s => {
#         const lat = Number(s.lat), lon = Number(s.lon);
#         if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;

#         const status = (s.status || '').toLowerCase();
#         const color =
#           status === 'ok' ? '#2ecc71' :
#           status === 'warning' ? '#f39c12' :
#           status === 'error' ? '#e74c3c' : '#2980b9';

#         const m = L.circleMarker([lat, lon], { radius: 6, color, weight: 2, fillOpacity: 0.9 }).addTo(map);
#         const label = s.label || s.name || s.sensor_id || '';
#         const bat = s.battery != null ? `Battery: ${s.battery}` : '';
#         const moi = s.moisture != null ? `Moisture: ${s.moisture}` : '';
#         m.bindTooltip(`<b>${label}</b><br/>${bat}<br/>${moi}`, { direction: 'top', opacity: 0.9 });
#       });
#     }).catch(err => console.error('Failed to load sensors:', err));
#   </script>
# </body>
# </html>
#     """.strip()
#     return Response(html, mimetype="text/html")



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
