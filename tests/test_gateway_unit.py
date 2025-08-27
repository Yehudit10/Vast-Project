import json
import uuid
import pytest
from httpx import AsyncClient
from asgi_lifespan import LifespanManager
from gateway.app import create_app
import grpc

class FakeAioRpcError(grpc.aio.AioRpcError):
    def __init__(self, code: grpc.StatusCode, details: str = ""):
        self._code = code
        self._details = details
    def code(self): return self._code
    def details(self): return self._details
    def __repr__(self):  # nice for pytest output
        return f"FakeAioRpcError(code={self._code.name}, details={self._details!r})"

class HappyStub:
    async def RunQuery(self, req, *, metadata=None, timeout=None):
        parsed = json.loads(req.json)
        assert isinstance(parsed, dict)
        class _Resp:
            jobId = "job-123"
            status = 2  # SUBMITTED
        assert ("x-request-id", metadata[0][1]) in metadata
        return _Resp()

class FailingStub:
    def __init__(self, error): self._error = error
    async def RunQuery(self, req, *, metadata=None, timeout=None):
        raise self._error

@pytest.mark.asyncio
async def test_runquery_happy_path():
    app = create_app(stub=HappyStub())
    rid = str(uuid.uuid4())
    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            r = await ac.post("/runQuery",
                              json={"ops":[{"op":"select","fields":["sensor"]}]},
                              headers={"X-Request-Id": rid})
    assert r.status_code == 202
    j = r.json()
    assert j["requestId"] == rid
    assert j["jobId"] == "job-123"
    assert j["status"] == "SUBMITTED"
    assert j["detailsUrl"] == f"/jobs/{j['jobId']}"

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, expected_http",
    [
        (FakeAioRpcError(grpc.StatusCode.INVALID_ARGUMENT, "bad plan"), 400),
        (FakeAioRpcError(grpc.StatusCode.DEADLINE_EXCEEDED, ""),         504),
        (FakeAioRpcError(grpc.StatusCode.UNAVAILABLE, ""),               503),
        (FakeAioRpcError(grpc.StatusCode.UNIMPLEMENTED, ""),             501),
        (FakeAioRpcError(grpc.StatusCode.INTERNAL, "boom"),              502),
    ],
)
async def test_runquery_error_mapping(error, expected_http):
    app = create_app(stub=FailingStub(error))
    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            r = await ac.post("/runQuery", json={"ops":[]})
    assert r.status_code == expected_http



