# from __future__ import annotations
# import os
# import uuid
# import typing as t

# try:
#     import requests
# except Exception as e:  
#     raise RuntimeError("Please install 'requests' (pip install requests)") from e

# GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")

# def get_sensors() -> list[dict]:
#     """
#     reads the list of sensors from the gateway according to the DSL you provided.
#     returns list[dict] with keys like: sensor_id, lat, lon, status, name, label, battery, moisture.
#     """
#     plan = {
#         "source": "sensors",
#         "_ops": [
#             {"op": "select", "columns": [
#                 "sensor_id","lat","lon","status","name","label","battery","moisture"
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
#     resp = requests.post(f"{GATEWAY_URL}/runQuery", json=plan, headers=headers, timeout=30)
#     resp.raise_for_status()
#     data: t.Any = resp.json()

#     # gentle validation + filtering
#     out: list[dict] = []
#     if isinstance(data, list):
#         for row in data:
#             if not isinstance(row, dict):
#                 continue
#             try:
#                 lat = float(row["lat"])
#                 lon = float(row["lon"])
#             except Exception:
#                 continue
#             out.append(row)
#     return out
from __future__ import annotations
import os
import uuid
import typing as t

try:
    import requests
except Exception as e:  
    raise RuntimeError("Please install 'requests' (pip install requests)") from e

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000")
SENSORS_PATH = os.getenv("SENSORS_PATH", "")

def _normalize(rows: t.Any) -> list[dict]:
    if isinstance(rows, dict):
        rows = rows.get("sensors", [])
    out = []
    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            sid = r.get("sensor_id") or r.get("id") or r.get("sensorId")
            lat = r.get("lat") or r.get("latitude")
            lon = r.get("lon") or r.get("lng") or r.get("longitude")
            if sid is None or lat is None or lon is None:
                continue
            out.append({
                "sensor_id": str(sid),
                "lat": float(lat),
                "lon": float(lon),
                "label": r.get("label") or r.get("name") or str(sid),
                "status": r.get("status", ""),
                "battery": r.get("battery"),
                "moisture": r.get("moisture"),
                "last_seen": r.get("last_seen"),
                # "hover": r.get("hover"),
                "data": r,
            })
    return out

# def get_sensors() -> list[dict]:
#     """
#     reads the list of sensors from the gateway according to the DSL you provided.
#     returns list[dict] with keys like: sensor_id, lat, lon, status, name, label, battery, moisture.
#     """
#     plan = {
#         "source": "sensors",
#         "_ops": [
#             {"op": "select", "columns": [
#                 "sensor_id","lat","lon","status","name","label","battery","moisture"
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
#         resp = requests.post(f"{GATEWAY_URL}/runQuery", json=plan, headers=headers, timeout=30)
#         resp.raise_for_status()
#         data: t.Any = resp.json()
#     except requests.exceptions.ConnectionError:
#         print("WARNING: Could not connect to sensors API! Returning empty list.")
#         data: t.Any = []
#     except Exception as e:
#         print(f"ERROR: Failed to fetch sensors: {e}")
#         data: t.Any = []
#     # gentle validation + filtering
#     out: list[dict] = []
#     if isinstance(data, list):
#         for row in data:
#             if not isinstance(row, dict):
#                 continue
#             try:
#                 lat = float(row["lat"])
#                 lon = float(row["lon"])
#             except Exception:
#                 continue
#             out.append(row)
#     return out

def get_sensors() -> list[dict]:
    """
    Try the current service endpoint first (GET /api/sensors).
    If not available, fallback to legacy POST /runQuery.
    Returns a normalized list of dicts with at least: sensor_id, lat, lon.
    """
    # --- 1) try GET /api/sensors (services/webmap.py / sensors_metrics_app.py) ---
    path = SENSORS_PATH or "/api/sensors"
    try:
        resp = requests.get(f"{GATEWAY_URL}{path}", timeout=5)
        resp.raise_for_status()
        return _normalize(resp.json())
    except Exception as e:
        print(f"[SENSORS] GET {path} failed: {e}")

    # --- 2) fallback: legacy gateway DSL via POST /runQuery ---
    plan = {
        "source": "sensors",
        "_ops": [
            {"op": "select", "columns": [
                "sensor_id", "lat", "lon", "status", "name", "label", "battery", "moisture"
            ]},
            {"op": "where", "cond": {
                "any": [
                    {"op": "=", "left": {"col": "status"}, "right": {"literal": "ok"}},
                    {"op": "=", "left": {"col": "status"}, "right": {"literal": "warning"}}
                ]
            }}
        ]
    }
    headers = {
        "Content-Type": "application/json",
        "X-Request-Id": str(uuid.uuid4()),
    }
    try:
        resp = requests.post(f"{GATEWAY_URL}/runQuery", json=plan, headers=headers, timeout=10)
        resp.raise_for_status()
        return _normalize(resp.json())
    except requests.exceptions.ConnectionError:
        print("WARNING: Could not connect to sensors API! Returning empty list.")
        return []
    except Exception as e:
        print(f"ERROR: Failed to fetch sensors via /runQuery: {e}")
        return []
