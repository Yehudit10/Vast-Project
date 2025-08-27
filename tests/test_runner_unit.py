# tests/test_runner_unit.py
import json
import uuid
import types
import pytest
import grpc
from runner import runner_server
import query_pb2

class _FakeContext:
    def __init__(self, md=None):
        self._aborted = None
        self._details = None
        self._md = md or []
    def invocation_metadata(self):
        return self._md
    def abort(self, code, details):
        # Emulate gRPC abort by raising an RpcError
        err = grpc.RpcError()
        err.code = lambda: code
        err.details = lambda: details
        raise err

def _plan(json_str: str) -> query_pb2.Plan:
    return query_pb2.Plan(json=json_str)

def test_runquery_mock_happy(monkeypatch):
    # Force mock mode
    monkeypatch.setattr(runner_server, "RUNNER_MODE", "mock", raising=True)
    srv = runner_server.QueryRunnerImpl()
    ctx = _FakeContext(md=[("x-request-id", "abc-123")])
    resp = srv.RunQuery(_plan(json.dumps({"ops": []})), ctx)
    assert resp.status == query_pb2.Status.SUBMITTED
    assert resp.jobId.startswith("mock-")

def test_runquery_invalid_json_maps_to_invalid_argument(monkeypatch):
    monkeypatch.setattr(runner_server, "RUNNER_MODE", "mock", raising=True)
    srv = runner_server.QueryRunnerImpl()
    ctx = _FakeContext()
    with pytest.raises(grpc.RpcError) as ei:
        srv.RunQuery(_plan("not-json"), ctx)
    assert ei.value.code().name == "INVALID_ARGUMENT"

def test_runquery_real_mode_is_unimplemented(monkeypatch):
    monkeypatch.setattr(runner_server, "RUNNER_MODE", "real", raising=True)
    srv = runner_server.QueryRunnerImpl()
    ctx = _FakeContext()
    with pytest.raises(grpc.RpcError) as ei:
        srv.RunQuery(_plan(json.dumps({"ops": []})), ctx)
    assert ei.value.code().name == "UNIMPLEMENTED"
