# runner_server.py (replace the earlier file)

import os, json, uuid, logging, time
from concurrent import futures
from typing import Dict, Any
import grpc
import query_pb2, query_pb2_grpc
# import requests  # sync is fine; runner uses sync gRPC

RUNNER_MODE = os.getenv("RUNNER_MODE", "mock")  # "mock" or "real"
SQL_GATEWAY = os.getenv("FLINK_SQL_GATEWAY_URL", "http://flink-sql-gateway:8083")  # adjust
PORT = int(os.getenv("PORT", "50051"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("runner")

class QueryRunnerImpl(query_pb2_grpc.QueryRunnerServicer):
    def RunQuery(self, request, context):
        md = dict(context.invocation_metadata())
        request_id = md.get("x-request-id", str(uuid.uuid4()))
        log.info("RunQuery request_id=%s mode=%s", request_id, RUNNER_MODE)

        # Parse the JSON plan (optionally extract SQL)
        try:
            plan: Dict[str,Any] = json.loads(request.json) if request.json else {}
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

        # --- REAL: fetch sensors from Flink SQL Gateway ---
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "Real runner is not implemented")

def _pack_sensors(sensors_list):
    """Convert list[dict] → query_pb2.SensorList."""
    result = query_pb2.SensorList()
    for s in sensors_list:
        sensor = query_pb2.Sensor(
            sensor_id=str(s.get("sensor_id", "")),
            lat=float(s.get("lat", 0.0)),
            lon=float(s.get("lon", 0.0)),
        )
        # move the rest into props (strings)
        for k, v in s.items():
            if k in ("sensor_id", "lat", "lon"): continue
            sensor.props[k] = "" if v is None else str(v)
        result.sensors.append(sensor)
    return result

def serve(port: int = PORT):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    query_pb2_grpc.add_QueryRunnerServicer_to_server(QueryRunnerImpl(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("Runner gRPC listening on :%s (mode=%s)", port, RUNNER_MODE)
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
