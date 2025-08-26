# gateway_main.py
"""
Gateway service (FastAPI → gRPC):
- Exposes POST /runQuery to accept a JSON plan.
- Forwards the plan to the runner over gRPC with a deadline and request tracing.
"""

import os, uuid, json, logging
from typing import Any
from fastapi import FastAPI, HTTPException, Request, Body, status as http_status
from pydantic import BaseModel, ConfigDict
from contextlib import asynccontextmanager
import grpc
import query_pb2, query_pb2_grpc

# Address of the runner (gRPC) service
RUNNER_ADDR = os.getenv("RUNNER_ADDR", "localhost:50051")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("gateway")

# ---------- Pydantic models ----------
class PlanModel(BaseModel):
    """
    Permissive plan model:
    - Ensures top-level is an object; allows extra keys so the DSL can evolve.
    - Optionally declares 'ops' for light structure without strict validation.
    """
    model_config = ConfigDict(extra="allow")
    ops: list[Any] | None = None

class RunResponseModel(BaseModel):
    """Response contract returned to HTTP clients."""
    requestId: str
    jobId: str
    status: str
    detailsUrl: str

# ---------- FastAPI app ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    App lifecycle:
    - Startup: create and store gRPC channel + stub.
    - Shutdown: close channel.
    """
    channel = grpc.aio.insecure_channel(RUNNER_ADDR)
    stub = query_pb2_grpc.QueryRunnerStub(channel)
    app.state.channel = channel
    app.state.stub = stub
    log.info("gateway_startup (runner_addr=%s)", RUNNER_ADDR)

    try:
        yield
    finally:
        try:
            await channel.close()
        except Exception as e:
            log.warning("gateway_shutdown_error: %s", e)
        log.info("gateway_shutdown")

app = FastAPI(title="Query Gateway (FastAPI → gRPC Runner)", lifespan=lifespan)

@app.post("/runQuery", response_model=RunResponseModel, status_code=http_status.HTTP_202_ACCEPTED)
async def run_query(plan: PlanModel = Body(...), request: Request=None) -> RunResponseModel:
    """
    Accept a JSON plan, forward to the runner via gRPC, and return job metadata.

    Behavior:
    - Uses/creates X-Request-Id for traceability.
    - Serializes the plan and sends it as query_pb2.Plan(json=...).
    - Applies a 15s gRPC timeout to prevent hanging.
    - Maps gRPC errors to HTTP 4xx/5xx codes.
    """
    # Trace id (propagate if provided by client)
    request_id = request.headers.get("X-Request-Id", str(uuid.uuid4()))

    # Serialize to JSON; reject if not serializable
    try:
        payload = json.dumps(plan.model_dump())
    except Exception as e:
        log.error("plan_serialization_error request_id=%s err=%s", request_id, e)
        raise HTTPException(status_code=400, detail="Invalid plan")

    log.info("run_query_received request_id=%s size=%dB", request_id, len(payload))

    try:
        # Propagate request id via gRPC metadata for end-to-end tracing
        metadata = (("x-request-id", request_id),)

        # Call runner with a deadline to avoid hanging
        resp = await app.state.stub.RunQuery(
            query_pb2.Plan(json=payload),
            metadata=metadata,
            timeout=15.0,
        )

        result = {
            "requestId": request_id,
            "jobId": resp.jobId,
            "status": query_pb2.Status.Name(resp.status),  # convert enum to string
            "detailsUrl": f"/jobs/{resp.jobId}",           # consider making this absolute via BASE_URL
        }
        log.info("run_query_success request_id=%s job_id=%s status=%s",
                 request_id, result["jobId"], result["status"])
        return result

    except grpc.aio.AioRpcError as e:
        # Map runner errors to clear HTTP statuses for clients
        code = e.code()
        detail = e.details() or ""
        log.error("runner_rpc_error request_id=%s code=%s detail=%s", request_id, code.name, detail)
        if code == grpc.StatusCode.INVALID_ARGUMENT:
            raise HTTPException(status_code=400, detail=detail)
        if code == grpc.StatusCode.DEADLINE_EXCEEDED:
            raise HTTPException(status_code=504, detail="Runner deadline exceeded")
        if code == grpc.StatusCode.UNAVAILABLE:
            raise HTTPException(status_code=503, detail="Runner unavailable")
        if code == grpc.StatusCode.UNIMPLEMENTED:
            raise HTTPException(status_code=501, detail="Runner feature not implemented")
        raise HTTPException(status_code=502, detail=f"Runner error: {code.name} - {detail}")

    except Exception:
        log.exception("gateway_unhandled_error request_id=%s", request_id)
        raise HTTPException(status_code=500, detail="Internal server error")
