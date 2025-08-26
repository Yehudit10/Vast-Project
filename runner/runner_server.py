# runner_server.py
"""
Runner service (gRPC):
- Implements QueryRunner.RunQuery to receive a JSON plan from the gateway.
- Validates JSON syntactically and (in mock mode) returns a fake job id.
- Real mode is left unimplemented to be wired into Flink REST later.
"""

import os, json, uuid, logging
from concurrent import futures
import grpc
import query_pb2, query_pb2_grpc

# -------- Config --------
RUNNER_MODE = os.getenv("RUNNER_MODE", "mock")                 # "mock" or "real"
FLINK_REST_URL = os.getenv("FLINK_REST_URL", "http://flink:8081")  # used in 'real' mode
PORT = int(os.getenv("PORT", "50051"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# -------- Logging --------
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("runner")

class QueryRunnerImpl(query_pb2_grpc.QueryRunnerServicer):
    """gRPC servicer implementing the QueryRunner API."""

    def RunQuery(self, request, context):
        """
        Handle a submitted plan:
        - Extract x-request-id from metadata (or generate one) for tracing.
        - Parse and minimally validate the plan JSON.
        - In 'mock' mode, return a fake job id with Status.SUBMITTED.
        - In 'real' mode, abort with UNIMPLEMENTED (placeholder for Flink).
        """
        # Correlate logs across gateway/runner
        md = dict(context.invocation_metadata())
        request_id = md.get("x-request-id", str(uuid.uuid4()))
        log.info("RunQuery called request_id=%s mode=%s", request_id, RUNNER_MODE)

        # Basic JSON validation only (structure/content checks are out of scope here)
        try:
            plan = json.loads(request.json)
            log.info("Plan received request_id=%s keys=%s", request_id, list(plan.keys()))
        except Exception as e:
            log.error("Invalid plan JSON request_id=%s error=%s", request_id, e)
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "Invalid plan JSON")

        if RUNNER_MODE == "mock":
            # Simulate async job submission and return an enum status
            job_id = f"mock-{uuid.uuid4().hex[:8]}"
            log.info("Mock job submitted request_id=%s job_id=%s", request_id, job_id)
            return query_pb2.RunResponse(jobId=job_id, status=query_pb2.Status.SUBMITTED)

        # Real mode: compile plan → Flink REST (not implemented yet)
        log.warning("Real mode not implemented request_id=%s flink_url=%s", request_id, FLINK_REST_URL)
        context.abort(grpc.StatusCode.UNIMPLEMENTED,
                      "RUNNER_MODE=real not implemented in this example")

# -------- Server bootstrap --------
def serve(port: int = PORT):
    """
    Start the gRPC server:
    - Registers the QueryRunner servicer.
    - Binds to [::]:PORT (insecure for local/dev; add TLS in prod).
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    query_pb2_grpc.add_QueryRunnerServicer_to_server(QueryRunnerImpl(), server)
    server.add_insecure_port(f"[::]:{port}")
    server.start()
    log.info("Runner gRPC listening on :%s (mode=%s)", port, RUNNER_MODE)
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
