# AgCloud
# VAST Dashboard (PyQt6 + Grafana + Orthophoto + Sensors Gateway)

A desktop monitoring dashboard built with **PyQt6**. It combines three data layers on a single Home screen:

- **Grafana embeds (demo):** two Grafana panels rendered via QWebEngine (Prometheus demo data; not related to the map sensors).
- **Orthophoto map:** a fast tiled orthophoto viewer (QGraphicsView/QGraphicsScene) with smooth zoom & pan.
- **Live sensor overlay (real):** a DSL → SQL gateway backed by a gRPC runner querying a SQLite database and returning sensor rows that are plotted on the map.

## Components

- `auth_ui/` – Login/Signup pages and a small in-memory auth service (app starts on Login; successful sign-in opens the main window; Logout returns to Login).
- `orthophoto_canvas/` – Tiled viewer (`ui/viewer.py`), sensor overlay (`ui/sensors_layer.py`), data access (`ag_io/sensors_api.py`).
- `dsl/` – A compact query DSL (JSON plan).
- `runner/` – gRPC server executing SQL against SQLite (`data/app.db`).
- `gateway/` – FastAPI app exposing `/runQuery`; translates DSL to SQL, calls the runner, and returns JSON.
- `services/` – Flask utilities (Prometheus demo exporter, optional simple web map).
- `grafana/`, `prometheus/` – Dockerized Grafana/Prometheus for the demo panels.
- `main.py`, `main_window.py`, `home_view.py` – Desktop shell (menu, navigation, and Home layout: Grafana on top, orthophoto below).

## Environment

- `GATEWAY_URL` – FastAPI gateway base URL (default `http://127.0.0.1:9001`).
- `RUNNER_ADDR` – gRPC runner address (default `localhost:50051`).
- `RUNNER_DB` – Absolute path to the SQLite DB (e.g. `<repo>/data/app.db`).
- `SENSORS_PATH` – Optional endpoint path override for GET sensors (defaults to `/api/sensors`). For file-based fallback use a different variable name (see code comments).

## Typical runtime (3 terminals)

1) Runner (gRPC → SQLite):
   - `set RUNNER_DB=<ABS>\data\app.db` (Windows PowerShell: `$env:RUNNER_DB = (Resolve-Path .\data\app.db).Path`)
   - `python -m runner.runner_server`

2) Gateway (FastAPI):
   - `python -m uvicorn gateway.app:create_app --factory --host 127.0.0.1 --port 9001`

3) Desktop app:
   - `set GATEWAY_URL=http://127.0.0.1:9001` (PowerShell: `$env:GATEWAY_URL = "http://127.0.0.1:9001"`)
   - `python .\main.py`

(Optional) Grafana/Prometheus demo:
- `docker compose up -d prometheus grafana`



Required installations:
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip wheel
pip install -r requirements.txt
pip install --only-binary=:all: PyQt6 PyQt6-WebEngine grpcio grpcio-tools
pip install fastapi uvicorn requests prometheus-client

Running:
docker compose up -d prometheus grafana
docker compose ps

## Terminal A:
.\.venv\Scripts\Activate.ps1
$env:SQLITE_DB = "/C:/Users/sara/Documents/login-and-gui/data/app.db"
python -m runner.runner_server

## Terminal B:
.\.venv\Scripts\Activate.ps1
python -m uvicorn gateway.app:create_app --factory --host 127.0.0.1 --port 9001

## Terminal C:
.\.venv\Scripts\Activate.ps1
python -m services.sensors_metrics_app

## Terminal D:
.\.venv\Scripts\Activate.ps1
$env:GATEWAY_URL = "http://127.0.0.1:9001"
python .\main.py
