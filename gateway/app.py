"""
Gateway service (FastAPI → gRPC) with an app factory.

- create_app(runner_addr=None, stub=None) builds the FastAPI app.
- You can inject a fake gRPC stub in tests via the `stub` argument.
"""

import os, uuid, json, logging
from typing import Any
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

class RunResponseModel(BaseModel):
    """Response contract returned to HTTP clients."""
    requestId: str
    jobId: str
    status: str
    detailsUrl: str

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

    @app.post("/runQuery", response_model=RunResponseModel, status_code=http_status.HTTP_202_ACCEPTED)
    async def run_query(request: Request, plan: PlanModel = Body(...)) -> RunResponseModel:
        """
        Accept a JSON plan, forward to the runner via gRPC, and return job metadata.
        - Propagates/creates X-Request-Id.
        - Sends plan as query_pb2.Plan(json=...).
        - 15s timeout on the RPC.
        - Maps gRPC errors to HTTP codes.
        """
        request_id = (request.headers.get("X-Request-Id") if request else None) or str(uuid.uuid4())

        # Serialize to JSON; reject if not serializable
        try:
            payload = json.dumps(plan.model_dump())
        except Exception as e:
            log.error("plan_serialization_error request_id=%s err=%s", request_id, e)
            raise HTTPException(status_code=400, detail="Invalid plan")

        log.info("run_query_received request_id=%s size=%dB", request_id, len(payload))

        try:
            metadata = (("x-request-id", request_id),)
            resp = await app.state.stub.RunQuery(
                query_pb2.Plan(json=payload),
                metadata=metadata,
                timeout=15.0,
            )

            result = {
                "requestId": request_id,
                "jobId": resp.jobId,
                "status": query_pb2.Status.Name(resp.status),
                "detailsUrl": f"/jobs/{resp.jobId}",
            }
            log.info("run_query_success request_id=%s job_id=%s status=%s",
                     request_id, result["jobId"], result["status"])
            return result

        except grpc.aio.AioRpcError as e:
            code = e.code()
            detail = e.details() or ""
            log.error("runner_rpc_error request_id=%s code=%s detail=%s", request_id, code.name, detail)

            match code:
                case grpc.StatusCode.INVALID_ARGUMENT:
                    raise HTTPException(status_code=400, detail=detail)
                case grpc.StatusCode.DEADLINE_EXCEEDED:
                    raise HTTPException(status_code=504, detail="Runner deadline exceeded")
                case grpc.StatusCode.UNAVAILABLE:
                    raise HTTPException(status_code=503, detail="Runner unavailable")
                case grpc.StatusCode.UNIMPLEMENTED:
                    raise HTTPException(status_code=501, detail="Runner feature not implemented")
                case _:
                    raise HTTPException(status_code=502, detail=f"Runner error: {code.name} - {detail}")

        except Exception:
            log.exception("gateway_unhandled_error request_id=%s", request_id)
            raise HTTPException(status_code=500, detail="Internal server error")

    return app
