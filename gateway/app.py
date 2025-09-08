"""
Gateway service (FastAPI → gRPC) with an app factory.

Strict plan validation for the DSL:
- Plan: {"source": str, "_ops": [SelectOp | WhereOp]}
- SelectOp: {"op":"select","columns":[str,...]}
- WhereOp:  {"op":"where","cond": Cond}
- Cond: {"all":[Cond,...]} | {"any":[Cond,...]} | {"op":OP,"left":Leaf,"right":Leaf}
- Leaf: {"col": str} | {"literal": JSON}
- OP: one of "=", "!=", "<", "<=", ">", ">="
"""

from __future__ import annotations

import os, uuid, json, logging
from typing import Any, Union, List, Mapping
from fastapi import FastAPI, HTTPException, Request, Body
from fastapi import status as http_status
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from contextlib import asynccontextmanager
import grpc
import query_pb2, query_pb2_grpc

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("gateway")

# ---------- Strict Plan Models (Pydantic v2) ----------

ALLOWED_BIN_OPS = {"=", "!=", "<", "<=", ">", ">="}

class ColLeaf(BaseModel):
    model_config = ConfigDict(extra="forbid")
    col: str

class LiteralLeaf(BaseModel):
    model_config = ConfigDict(extra="forbid")
    literal: Any

Leaf = Union[ColLeaf, LiteralLeaf]

class PredicateCond(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str
    left: Leaf
    right: Leaf

    def model_post_init(self, _context):
        if self.op not in ALLOWED_BIN_OPS:
            raise ValueError(f"Operator {self.op!r} not allowed. Allowed: {sorted(ALLOWED_BIN_OPS)}")

class AllCond(BaseModel):
    model_config = ConfigDict(extra="forbid")
    all: List["Cond"]  # forward ref

class AnyCond(BaseModel):
    model_config = ConfigDict(extra="forbid")
    any: List["Cond"]

Cond = Union[AllCond, AnyCond, PredicateCond]
AllCond.model_rebuild()
AnyCond.model_rebuild()

class SelectOpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str
    columns: List[str]

    def model_post_init(self, _context):
        if self.op != "select":
            raise ValueError("Select op 'op' must be 'select'")
        if not self.columns:
            raise ValueError("Select op requires non-empty 'columns'")

class WhereOpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str
    cond: Cond

    def model_post_init(self, _context):
        if self.op != "where":
            raise ValueError("Where op 'op' must be 'where'")

OpModel = Union[SelectOpModel, WhereOpModel]

class PlanModel(BaseModel):
    """
    Strict Plan: exactly {"source": str, "_ops": [OpModel,...]}.
    We forbid extras and use alias for `_ops`.
    """
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    source: str
    ops_: List[OpModel] = Field(alias="_ops")

# ---------- Response model (unchanged) ----------

class SensorModel(BaseModel):
    sensor_id: str
    lat: float
    lon: float
    model_config = ConfigDict(extra="allow")  # passthrough props


# ---------- Utilities ----------

_ERROR_MAP: dict[grpc.StatusCode, tuple[int, str | None]] = {
    grpc.StatusCode.INVALID_ARGUMENT: (400, None),
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

# ---------- App Factory ----------

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

    @app.post("/runQuery", response_model=List[SensorModel], status_code=http_status.HTTP_200_OK)
    async def run_query(request: Request, plan: PlanModel = Body(...)) -> List[SensorModel]:
        """
        Accept a strict JSON plan, forward to the runner via gRPC, and return sensors.
        - Propagates/creates X-Request-Id (also returned as a response header by infra, if desired).
        - Sends plan as query_pb2.Plan(json=...).
        - 30s timeout on the RPC (configurable via env / edit here).
        - Maps gRPC errors to HTTP codes.
        """
        request_id = (request.headers.get("X-Request-Id") if request else None) or str(uuid.uuid4())

        # Validate & serialize STRICT plan (by_alias=True to emit "_ops")
        try:
            payload_dict = plan.model_dump(by_alias=True)
            payload = json.dumps(payload_dict, separators=(",", ":"))
        except ValidationError as e:
            log.error("plan_validation_error request_id=%s err=%s", request_id, e)
            raise HTTPException(status_code=400, detail="Invalid plan")
        except Exception as e:
            log.error("plan_serialization_error request_id=%s err=%s", request_id, e)
            raise HTTPException(status_code=400, detail="Invalid plan")

        log.info("run_query_received request_id=%s size=%dB", request_id, len(payload))

        try:
            metadata = (("x-request-id", request_id),)
            resp = await app.state.stub.RunQuery(
                query_pb2.Plan(json=payload),
                metadata=metadata,
                timeout=30.0,
            )
        except grpc.aio.AioRpcError as e:
            log.error("runner_rpc_error request_id=%s code=%s detail=%s",
                      request_id, e.code().name, e.details() or "")
            raise _map_grpc_error(e)

        # Convert gRPC SensorList -> list[dict] (merge props map)
        sensors: List[SensorModel] = []
        for s in resp.sensors:
            row: Mapping[str, Any] = {"sensor_id": s.sensor_id, "lat": s.lat, "lon": s.lon, **dict(s.props)}
            sensors.append(SensorModel.model_validate(row))
        log.info("run_query_success request_id=%s sensors=%d", request_id, len(sensors))
        return sensors

    return app