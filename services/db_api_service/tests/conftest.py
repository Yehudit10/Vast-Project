import sys
import types
import pathlib
import re
import importlib
import pytest

# --- put services/db_api_service/ on sys.path ---
REPO = pathlib.Path(__file__).resolve().parents[2]
SERVICE_DIR = REPO / "services" / "db_api_service"
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))

# --- stub dotenv ---
dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *a, **k: None
sys.modules.setdefault("dotenv", dotenv_stub)

# --- stub pydantic (minimal) ---
_pyd = types.ModuleType("pydantic")

class _BaseModel:
    def __init__(self, **data):
        for k, v in data.items():
            setattr(self, k, v)
    def dict(self, *a, **k):
        return {k: getattr(self, k) for k in self.__dict__.keys()}
    def model_dump(self, *a, **k):
        return {k: getattr(self, k) for k in self.__dict__.keys()}

def _Field(default=None, **kwargs):
    return default

class _ValidationError(Exception):
    pass

class _RootModel(_BaseModel):
    pass

_pyd.BaseModel = _BaseModel
_pyd.Field = _Field
_pyd.NonNegativeInt = int
_pyd.ValidationError = _ValidationError
_pyd.RootModel = _RootModel
sys.modules.setdefault("pydantic", _pyd)

# --- stub fastapi (router + deps + security) ---
class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail

def Depends(fn):
    return ("DEPENDS", fn)

def Query(default=None, **_):
    return default

class _Route:
    def __init__(self, method, path, func, dependencies=None, status_code=None):
        self.method = method.upper()
        self.path = path
        self.func = func
        self.dependencies = dependencies or []
        self.status_code = status_code

class APIRouter:
    def __init__(self, prefix="", tags=None, dependencies=None):
        self.prefix = prefix or ""
        self.tags = tags or []
        self.dependencies = dependencies or []
        self.routes = []

    def add_api_route(self, path, func, methods=None, status_code=None, dependencies=None):
        for m in (methods or ["GET"]):
            self.routes.append(
                _Route(m, self.prefix + path, func, (dependencies or []) + self.dependencies, status_code)
            )

    def include_router(self, router):
        for r in router.routes:
            combined = r.dependencies + self.dependencies
            self.routes.append(_Route(r.method, self.prefix + r.path, r.func, combined, r.status_code))

    def get(self, path, **kw):
        def deco(f):
            self.add_api_route(path, f, ["GET"], **kw)
            return f
        return deco

    def post(self, path, **kw):
        def deco(f):
            self.add_api_route(path, f, ["POST"], **kw)
            return f
        return deco

    def put(self, path, **kw):
        def deco(f):
            self.add_api_route(path, f, ["PUT"], **kw)
            return f
        return deco

    def delete(self, path, **kw):
        def deco(f):
            self.add_api_route(path, f, ["DELETE"], **kw)
            return f
        return deco

class FastAPI(APIRouter):
    def __init__(self, title="", version=""):
        super().__init__(prefix="")

class HTTPAuthorizationCredentials:
    def __init__(self, scheme, credentials):
        self.scheme = scheme
        self.credentials = credentials

class HTTPBearer:
    def __call__(self, header):
        if not header:
            return None
        parts = header.split(" ", 1)
        return HTTPAuthorizationCredentials(parts[0], parts[1]) if len(parts) == 2 else None

fastapi_stub = types.ModuleType("fastapi")
fastapi_stub.FastAPI = FastAPI
fastapi_stub.APIRouter = APIRouter
fastapi_stub.Depends = Depends
fastapi_stub.HTTPException = HTTPException
fastapi_stub.Query = Query

security_stub = types.ModuleType("fastapi.security")
security_stub.HTTPBearer = HTTPBearer
security_stub.HTTPAuthorizationCredentials = HTTPAuthorizationCredentials

sys.modules.setdefault("fastapi", fastapi_stub)
sys.modules.setdefault("fastapi.security", security_stub)

# --- ensure app package hierarchy exists if import fails ---
def _ensure_pkg(name):
    if name not in sys.modules:
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return sys.modules[name]

try:
    importlib.import_module("app.tables.files")
except ModuleNotFoundError:
    _ensure_pkg("app")
    _ensure_pkg("app.tables")
    _ensure_pkg("app.tables.files")

# --- repo mock with real signatures expected by router ---
repo = types.ModuleType("app.tables.files.repo")

def _list_files(bucket=None, device_id=None, limit=50):
    return []

def _upsert_file(data=None, **kwargs):
    return {"status": "ok"}

def _update_file(bucket, object_key, payload=None, **kwargs):
    return {"status": "ok"}

def _delete_file(bucket, object_key, **kwargs):
    return {"status": "deleted"}

repo.list_files  = _list_files
repo.upsert_file = _upsert_file
repo.update_file = _update_file
repo.delete_file = _delete_file

sys.modules["app.tables.files.repo"] = repo

# --- tiny TestClient (headers supported) ---
class Response:
    def __init__(self, code, data):
        self.status_code = code
        self._data = data
    def json(self):
        return self._data

class _ModelLike:
    def __init__(self, data):
        self._data = dict(data) if isinstance(data, dict) else data
    def model_dump(self, *args, **kwargs):
        return dict(self._data)
    def dict(self, *args, **kwargs):
        return dict(self._data)

class TestClient:
    def __init__(self, app):
        self.app = app

    def _match(self, method, path):
        for r in self.app.routes:
            if r.method != method.upper():
                continue
            pat = re.sub(r"\{([^}:]+):path\}", lambda m: f"(?P<{m.group(1)}>.+)", r.path)
            pat = re.sub(r"\{([^}:]+)\}",     lambda m: f"(?P<{m.group(1)}>[^/]+)", pat)
            m = re.match("^" + pat + "$", path)
            if m:
                return r, m.groupdict()
        return None, None

    def _run(self, method, path, headers=None, json=None):
        r, params = self._match(method, path)
        if not r:
            return Response(404, {"detail": "Not Found"})
        for dep in r.dependencies:
            if isinstance(dep, tuple) and dep[0] == "DEPENDS":
                creds = HTTPBearer()(headers.get("Authorization") if headers else None)
                if creds is None:
                    return Response(403, {"detail": "Not authenticated"})
                try:
                    dep[1](credentials=creds)
                except HTTPException as e:
                    return Response(e.status_code, {"detail": e.detail})
        kwargs = {}
        if json is not None and "payload" in r.func.__code__.co_varnames:
            kwargs["payload"] = _ModelLike(json)
        res = r.func(**(params or {}), **kwargs)
        return Response(r.status_code or (201 if method.upper() == "POST" else 200), res)

    def get(self, path, headers=None):
        return self._run("GET", path, headers=headers)

    def post(self, path, headers=None, json=None):
        return self._run("POST", path, headers=headers, json=json)

    def put(self, path, headers=None, json=None):
        return self._run("PUT", path, headers=headers, json=json)

    def delete(self, path, headers=None):
        return self._run("DELETE", path, headers=headers)

# --- fixtures ---
@pytest.fixture
def client_factory():
    from app.router import api
    app = FastAPI()
    app.include_router(api)
    return lambda: TestClient(app)

@pytest.fixture
def client_factory_main():
    from app.main import app
    return lambda: TestClient(app)
