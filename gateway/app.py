"""
Gateway service (FastAPI → gRPC) with an app factory.

- create_app(runner_addr=None, stub=None) builds the FastAPI app.
- You can inject a fake gRPC stub in tests via the `stub` argument.
"""

import os, uuid, json, logging
from typing import Any, Optional
from fastapi import FastAPI, HTTPException, Request, Body, status as http_status
from pydantic import BaseModel, ConfigDict
from contextlib import asynccontextmanager
import grpc
import query_pb2, query_pb2_grpc

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("gateway")

# ---------- Pydantic models ----------
class PlanModel(BaseModel):
    """Permissive plan model: top-level object, allows extra keys; optional `ops`."""
    model_config = ConfigDict(extra="allow")
    ops: list[Any] | None = None

class SensorModel(BaseModel):
    sensor_id: str
    lat: float
    lon: float
    # keep it permissive — extra props allowed
    model_config = ConfigDict(extra="allow")


# ---------- Utilities ----------
_ERROR_MAP: dict[grpc.StatusCode, tuple[int, str | None]] = {
    grpc.StatusCode.INVALID_ARGUMENT: (400, None),                          # use gRPC detail
    grpc.StatusCode.DEADLINE_EXCEEDED: (504, "Runner deadline exceeded"),
    grpc.StatusCode.UNAVAILABLE: (503, "Runner unavailable"),
    grpc.StatusCode.UNIMPLEMENTED: (501, "Runner feature not implemented"),
}

def _map_grpc_error(e: grpc.aio.AioRpcError) -> HTTPException:
    code = e.code()
    detail = e.details() or ""
    http_status_code, static_msg = _ERROR_MAP.get(code, (502, None))
    message = static_msg if static_msg is not None else detail or f"Runner error: {code.name}"
    return HTTPException(status_code=http_status_code, detail=message)

def create_app(*, runner_addr: str | None = None, stub: query_pb2_grpc.QueryRunnerStub | None = None) -> FastAPI:
    """
    Build a FastAPI app.
    - If `stub` is provided (tests), it's used directly.
    - Else we create a grpc.aio channel to `runner_addr` (or $RUNNER_ADDR / default).
    """
    runner_addr = runner_addr or os.getenv("RUNNER_ADDR", "localhost:50051")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if stub is not None:
            # Test mode: supplied stub, no channel to manage
            app.state.channel = None
            app.state.stub = stub
            log.info("gateway_startup (injected_stub)")
            yield
            log.info("gateway_shutdown (injected_stub)")
            return

        channel = grpc.aio.insecure_channel(runner_addr)
        app.state.channel = channel
        app.state.stub = query_pb2_grpc.QueryRunnerStub(channel)
        log.info("gateway_startup (runner_addr=%s)", runner_addr)
        try:
            yield
        finally:
            try:
                await channel.close()
            except Exception as e:
                log.warning("gateway_shutdown_error: %s", e)
            log.info("gateway_shutdown")

    app = FastAPI(title="Query Gateway (FastAPI → gRPC Runner)", lifespan=lifespan)

    
    @app.post("/runQuery", response_model=list[SensorModel], status_code=http_status.HTTP_200_OK)
    async def run_query(request: Request, plan: PlanModel = Body(...)) -> list[SensorModel]:
        """
        Accept a JSON plan, forward to the runner via gRPC, and return sensors.
        - Propagates/creates X-Request-Id (also returned as a response header).
        - Sends plan as query_pb2.Plan(json=...).
        - 30s timeout on the RPC (configurable via REQUEST_TIMEOUT_SECONDS).
        - Maps gRPC errors to HTTP codes.
        """

        request_id = (request.headers.get("X-Request-Id") if request else None) or str(uuid.uuid4())
        # Serialize and forward for validation / execution
        try:
            payload = json.dumps(plan.model_dump())
        except Exception as e:
            log.error("plan_serialization_error request_id=%s err=%s", request_id, e)
            raise HTTPException(status_code=400, detail="Invalid plan")

        log.info("run_query_received request_id=%s size=%dB", request_id, len(payload))

        try:
            metadata = (("x-request-id", request_id),)
            resp = await app.state.stub.RunQuery(query_pb2.Plan(json=payload),
                                                metadata=metadata, timeout=30.0)
        except grpc.aio.AioRpcError as e:
            log.error(
                "runner_rpc_error request_id=%s code=%s detail=%s",
                request_id, e.code().name, e.details() or "",
            )
            raise _map_grpc_error(e)
        
        # Convert gRPC SensorList -> list[dict] (merge props map)
        sensors: list[dict] = []
        for s in resp.sensors:
            row = {"sensor_id": s.sensor_id, "lat": s.lat, "lon": s.lon}
            row.update(dict(s.props))
            sensors.append(row)

        log.info("run_query_success request_id=%s sensors=%d", request_id, len(sensors))
        return sensors
    

    return app
