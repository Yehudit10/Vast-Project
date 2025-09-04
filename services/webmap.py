# from pathlib import Path
# from flask import Blueprint, send_from_directory, Response

# webmap_bp = Blueprint("webmap", __name__)

# TILES_ROOT = Path(__file__).resolve().parents[1] / "orthophoto_canvas" / "data" / "tiles"

# @webmap_bp.get("/tiles/<int:z>/<int:x>/<path:y_png>")
# def tiles(z: int, x: int, y_png: str):
#     p = TILES_ROOT / str(z) / str(x) / y_png
#     if p.is_file():
#         return send_from_directory(p.parent, p.name, mimetype="image/png")
#     try:
#         y = int(y_png.replace(".png", ""))
#         y_tms = (1 << z) - 1 - y
#         p2 = TILES_ROOT / str(z) / str(x) / f"{y_tms}.png"
#         if p2.is_file():
#             return send_from_directory(p2.parent, p2.name, mimetype="image/png")
#     except Exception:
#         pass
#     return Response("Tile not found", status=404)

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
#   <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
#   <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
#   <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
#   <style>
#     html,body,#map { height: 100%; margin: 0; }
#     .toolbar { position: absolute; top: 8px; left: 8px; z-index: 1000; background: #fff; padding: 6px 8px; border-radius: 6px; box-shadow: 0 1px 5px rgba(0,0,0,0.65); }
#     .toolbar label { font: 12px/1.4 sans-serif; margin-right: 6px; }
#     .coords { position: absolute; bottom: 6px; right: 8px; background: rgba(255,255,255,0.85); padding: 4px 6px; border-radius: 4px; font: 12px sans-serif; }
#   </style>
# </head>
# <body>
#   <div id="map"></div>
#   <div class="toolbar">
#     <label>Opacity <input id="opacity" type="range" min="0" max="1" value="1" step="0.05"></label>
#     <button id="home">Home</button>
#   </div>
#   <div class="coords" id="coords">Lat, Lon</div>

#   <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
#   <script src="https://unpkg.com/leaflet.fullscreen@2.4.0/Control.FullScreen.js"></script>
#   <script src="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.js"></script>
#   <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
#   <script>
#     const HOME = { center: [31.77, 35.21], zoom: 12 };
#     const map = L.map('map', { zoomControl: true }).setView(HOME.center, HOME.zoom);
#     L.control.fullscreen().addTo(map);
#     L.control.scale().addTo(map);

#     // Local orthophoto tiles (from orthophoto_canvas/data/tiles)
#     const ortho = L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19, minZoom: 0 });
#     ortho.addTo(map);

#     // Optional base map
#     const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{ maxZoom: 19, attribution: '&copy; OpenStreetMap' });

#     // Drawing/editing layer
#     const drawn = new L.FeatureGroup().addTo(map);
#     new L.Control.Draw({ edit: { featureGroup: drawn }, draw: { circle: false } }).addTo(map);
#     map.on(L.Draw.Event.CREATED, e => drawn.addLayer(e.layer));

#     // Layers control
#     const baseLayers = { "Orthophoto": ortho, "OSM": osm };
#     const overlays = { "Drawn": drawn };
#     L.control.layers(baseLayers, overlays, { collapsed: false }).addTo(map);

#     // Opacity slider
#     document.getElementById('opacity').addEventListener('input', (ev) => {
#       ortho.setOpacity(parseFloat(ev.target.value));
#     });

#     // Home button
#     document.getElementById('home').addEventListener('click', () => {
#       map.setView(HOME.center, HOME.zoom);
#     });

#     // Mouse coords
#     map.on('mousemove', (e) => {
#       document.getElementById('coords').textContent =
#         `${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`;
#     });

#     // Optional: markers from /api/sensors
#     fetch('/api/sensors').then(r => r.json()).then(rows => {
#       rows.forEach(s => {
#         if (typeof s.lat === 'number' && typeof s.lon === 'number') {
#           L.marker([s.lat, s.lon]).addTo(map).bindPopup(`<b>${s.id ?? 'sensor'}</b>`);
#         }
#       });
#     }).catch(() => {});
#   </script>
# </body>
# </html>
# """
#     return Response(html, mimetype="text/html")


# services/webmap.py
from __future__ import annotations
from pathlib import Path
from flask import Blueprint, send_from_directory, Response, jsonify

# זהו אותו מודול שה־viewer משתמש בו להצגת ה־sensors האמיתיים
from orthophoto_canvas.ag_io.sensors_api import get_sensors

webmap_bp = Blueprint("webmap", __name__)

# מצביע ל- <project-root>/orthophoto_canvas/data/tiles
TILES_ROOT = Path(__file__).resolve().parents[1] / "orthophoto_canvas" / "data" / "tiles"

@webmap_bp.get("/tiles/<int:z>/<int:x>/<path:y_png>")
def tiles(z: int, x: int, y_png: str):
    # XYZ
    p = TILES_ROOT / str(z) / str(x) / y_png
    if p.is_file():
        return send_from_directory(p.parent, p.name, mimetype="image/png")
    # Fallback ל-TMS (היפוך Y)
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
    # אותם נתונים כמו ב-viewer (לא דמו)
    rows = get_sensors()
    return jsonify(rows)

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
  <link rel="stylesheet" href="https://unpkg.com/leaflet-draw@1.0.4/dist/leaflet.draw.css"/>
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
  <script>
    const map = L.map('map', { zoomControl: true });
    L.control.fullscreen().addTo(map);
    L.control.scale().addTo(map);

    // שכבת אריחים מקומיים (Orthophoto)
    const ortho = L.tileLayer('/tiles/{z}/{x}/{y}.png', { maxZoom: 19, minZoom: 0, updateWhenIdle: true });
    ortho.addTo(map);

    // שכבת בסיס אופציונלית
    const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{ maxZoom: 19, attribution: '&copy; OpenStreetMap' });

    // שכבת ציור
    const drawn = new L.FeatureGroup().addTo(map);
    new L.Control.Draw({ edit: { featureGroup: drawn }, draw: { circle: false } }).addTo(map);

    const baseLayers = { "Orthophoto": ortho, "OSM": osm };
    const overlays = { "Drawn": drawn };
    L.control.layers(baseLayers, overlays, { collapsed: false }).addTo(map);

    // שקיפות אורתופוטו
    document.getElementById('opacity').addEventListener('input', (ev) => {
      ortho.setOpacity(parseFloat(ev.target.value));
    });

    // קואורדינטות עכבר
    map.on('mousemove', (e) => {
      document.getElementById('coords').textContent =
        `${e.latlng.lat.toFixed(6)}, ${e.latlng.lng.toFixed(6)}`;
    });

    // טעינת sensors אמיתיים מהשרת (אותו מקור כמו ה-viewer)
    fetch('/api/sensors').then(r => r.json()).then(rows => {
      const markers = [];
      rows.forEach(s => {
        if (typeof s.lat !== 'number' || typeof s.lon !== 'number') return;

        // צבע לפי סטטוס כמו ב-viewer (התאימי במידת הצורך)
        const status = (s.status || '').toLowerCase();
        const color =
          status === 'ok' ? '#2ecc71' :
          status === 'warning' ? '#f39c12' :
          status === 'error' ? '#e74c3c' : '#3498db';

        const m = L.circleMarker([s.lat, s.lon], {
          radius: 6, weight: 2, color: '#ffffff', fillColor: color, fillOpacity: 0.95
        }).addTo(map);

        // Tooltip על hover (כמו ב-screenshot)
        const name = s.name || s.label || s.sensor_id || 'sensor';
        const battery = (s.battery != null) ? `${s.battery}` : 'n/a';
        const html = `
          <div style="font: 13px/1.2 sans-serif">
            <b>${name}</b> <small>${s.sensor_id ?? ''}</small><br/>
            <span style="color:#2ecc71">•</span> Battery: ${battery}<br/>
            <span style="color:#555">•</span> Status: ${status || 'n/a'}<br/>
          </div>
        `;

        m.bindTooltip(html, { direction: 'top', sticky: true, opacity: 0.95, className: 'sensor-tip' });
        markers.push(m);
      });

      // התאמת תצוגה לכל החיישנים; אם אין—מרכז/זום ברירת מחדל
      if (markers.length) {
        const group = L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.2));
      } else {
        map.setView([31.77, 35.21], 12);
      }
    }).catch(() => {
      map.setView([31.77, 35.21], 12); // fallback
    });

    // כפתור "Home" חוזר לתחום כל החיישנים
    document.getElementById('home').addEventListener('click', () => {
      fetch('/api/sensors').then(r => r.json()).then(rows => {
        const pts = rows.filter(s => typeof s.lat === 'number' && typeof s.lon === 'number')
                        .map(s => [s.lat, s.lon]);
        if (pts.length) map.fitBounds(pts, { padding: [20,20] });
      });
    });
  </script>
</body>
</html>
"""
    return Response(html, mimetype="text/html")
