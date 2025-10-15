# runner_server.py
"""
gRPC runner that executes a JSON DSL plan on SQLite (or returns mock data).

RPC
- QueryRunner.RunQuery({ json: str }) -> SensorList

Env
- RUNNER_MODE: 'real' | 'mock'
- SQLITE_DB : path to SQLite file
- PORT      : gRPC port (default 50051)
- LOG_LEVEL : logging level
"""

import os, json, uuid, logging, sqlite3
from concurrent import futures
from typing import Dict, Any, List
import grpc
from vast.proto.generated import query_pb2, query_pb2_grpc

# === Config ===
RUNNER_MODE = os.getenv("RUNNER_MODE", "real")  # "mock" or "real"
SQLITE_DB = os.getenv("SQLITE_DB", "./app.db")  # path to your SQLite file
PORT = int(os.getenv("PORT", "50051"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("runner")

# === Import the DSL compiler (strict JSON IR → SQL) ===
# Assumes you added the multi-file package from earlier under 'dsl/' on PYTHONPATH.
from vast.dsl import SQLBuilder, SQLiteDialect

# ---------------- gRPC Service ---------------- #

class QueryRunnerImpl(query_pb2_grpc.QueryRunnerServicer):
    """Validates JSON; mock mode returns fixtures, real mode compiles plan→SQL and executes."""

    def RunQuery(self, request, context):
        md = dict(context.invocation_metadata())
        request_id = md.get("x-request-id", str(uuid.uuid4()))
        log.info("RunQuery request_id=%s mode=%s", request_id, RUNNER_MODE)

        # Parse the JSON plan (strict format only)
        try:
            if not request.json:
                context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Empty request.json")
            plan: Dict[str, Any] = json.loads(request.json)
        except Exception as e:
            log.error("Invalid plan JSON req=%s err=%s", request_id, e)
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid plan JSON")

        if RUNNER_MODE == "mock":
            sensors = [
        {"sensor_id":"A-101", "lat":31.8998, "lon":34.849524, "name":"Soil Probe A",
        "battery":"3.86V", "moisture":"21%", "status":"ok"},
        {"sensor_id":"D-404", "lat":31.8978, "lon":34.849524, "name":"Soil Probe B",
        "battery":"3.86V", "moisture":"21%", "status":"ok"},
        {"sensor_id":"E-505", "lat":31.8978, "lon":34.850924, "name":"Soil Probe C",
        "battery":"3.86V", "moisture":"21%", "status":"ok"},
        {"sensor_id":"B-202", "lat":31.8996, "lon":34.849524, "label":"Valve East 4",
        "battery":"3.55V", "status":"warning"},
        {"sensor_id":"C-303", "lat":31.8999,   "lon":34.851734,   "status":"offline"}  
    ]
            return _pack_sensors(sensors)

        # compile plan → SQL (SQLite) and execute ---
        try:
            sql, params = SQLBuilder(SQLiteDialect()).compile(plan)
        except Exception as e:
            log.exception("Plan compilation failed req=%s", request_id)
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, f"Plan compilation failed: {e}")

        log.debug("SQL req=%s: %s", request_id, sql)
        log.debug("Params req=%s: %s", request_id, params)

        try:
            # Read-only connection: file:... uri + mode=ro
            uri = f"file:{SQLITE_DB}?mode=ro"
            with sqlite3.connect(uri, uri=True) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute(sql, params)
                rows = cur.fetchall()
        except sqlite3.OperationalError as e:
            log.exception("SQLite error req=%s", request_id)
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, f"SQLite error: {e}")
        except Exception as e:
            log.exception("Query execution failed req=%s", request_id)
            context.abort(grpc.StatusCode.INTERNAL, f"Execution failed: {e}")

        # Map rows → SensorList
        sensors_list = _rows_to_sensors(rows)
        return sensors_list


# ---------------- Helpers ---------------- #

def _rows_to_sensors(rows: List[sqlite3.Row]) -> query_pb2.SensorList:
    """
    Convert query result rows → SensorList.
    We look for common columns: sensor_id, lat/latitude, lon/lng/longitude.
    Any other columns go into props (as strings).
    """
    result = query_pb2.SensorList()
    for row in rows:
        # Column name lookup (case-insensitive)
        colmap = {k.lower(): k for k in row.keys()}
        sid_key = _first_key(colmap, ["sensor_id", "id", "sensorid"])
        lat_key = _first_key(colmap, ["lat", "latitude", "y"])
        lon_key = _first_key(colmap, ["lon", "lng", "long", "longitude", "x"])

        sensor = query_pb2.Sensor(
            sensor_id=str(row[sid_key]) if sid_key else "",
            lat=float(row[lat_key]) if lat_key and row[lat_key] is not None else 0.0,
            lon=float(row[lon_key]) if lon_key and row[lon_key] is not None else 0.0,
        )

        # Put remaining columns into props (strings)
        skip = set(k for k in [sid_key, lat_key, lon_key] if k)
        for k in row.keys():
            if k in skip:
                continue
            v = row[k]
            sensor.props[k] = "" if v is None else str(v)

        result.sensors.append(sensor)
    return result


def _first_key(colmap: Dict[str, str], candidates) -> str | None:
    """Return original column name matching any candidate (case-insensitive)."""
    for c in candidates:
        if c in colmap:
            return colmap[c]
    return None


def _pack_sensors(sensors_list):
    """(kept for mock mode) list[dict] → SensorList."""
    result = query_pb2.SensorList()
    for s in sensors_list:
        sensor = query_pb2.Sensor(
            sensor_id=str(s.get("sensor_id", "")),
            lat=float(s.get("lat", 0.0)),
            lon=float(s.get("lon", 0.0)),
        )
        for k, v in s.items():
            if k in ("sensor_id", "lat", "lon"):
                continue
            sensor.props[k] = "" if v is None else str(v)
        result.sensors.append(sensor)
    return result


def serve(port: int = PORT):
    """Start the gRPC server and block."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    query_pb2_grpc.add_QueryRunnerServicer_to_server(QueryRunnerImpl(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("Runner gRPC listening on :%s (mode=%s, db=%s)", port, RUNNER_MODE, SQLITE_DB)
    server.wait_for_termination()


if __name__ == "__main__":
    serve()





