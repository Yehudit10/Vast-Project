# AgCloud
# VAST Dashboard (PyQt6 + Grafana + Orthophoto + Sensors Gateway)

A desktop monitoring dashboard built with **PyQt6**. It combines three data layers on a single Home screen:

- **Grafana embeds (demo):** two Grafana panels rendered via QWebEngine (Prometheus demo data; not related to the map sensors).
- **Orthophoto map:** a fast tiled orthophoto viewer (QGraphicsView/QGraphicsScene) with smooth zoom & pan.
- **Live sensor overlay (real):** a DSL → SQL gateway backed by a gRPC runner querying a SQLite database and returning sensor rows that are plotted on the map.

## Components

- `src/vast/auth_ui/` – Login/Signup pages and a small in-memory auth service (app starts on Login; successful sign-in opens the main window; Logout returns to Login).
- `src/vast/orthophoto_canvas/` – Tiled viewer (`ui/viewer.py`), sensor overlay (`ui/sensors_layer.py`), data access (`ag_io/sensors_api.py`).
- `src/vast/dsl/` – A compact query DSL (JSON plan).
- `src/vast/runner/` – gRPC server executing SQL against SQLite (`data/app.db`).
- `src/vast/gateway/` – FastAPI app exposing `/runQuery`; translates DSL to SQL, calls the runner, and returns JSON.
- `src/vast/services/` – Flask utilities (Prometheus demo exporter, optional simple web map).
- `grafana/`, `prometheus/` – Dockerized Grafana/Prometheus for the demo panels.
- `src/vast/main.py`, `src/vast/main_window.py`, `src/vast/home_view.py` – Desktop shell (menu, navigation, and Home layout: Grafana on top, orthophoto below).

## Environment

- `GATEWAY_URL` – FastAPI gateway base URL (default `http://127.0.0.1:9001`).
- `RUNNER_ADDR` – gRPC runner address (default `localhost:50051`).
- `RUNNER_DB` – Absolute path to the SQLite DB (e.g. `<repo>/data/app.db`).
- `SENSORS_PATH` – Optional endpoint path override for GET sensors (defaults to `/api/sensors`). For file-based fallback use a different variable name (see code comments).
**Tip:** If you see “unable to open database file”, pass an **absolute** path with **forward slashes** as shown above.


## Prerequisites

- **Windows + PowerShell**
- **Python 3.12**
- **pip** (latest), **wheel**
- **Docker Desktop** (for Grafana/Prometheus demo)
- **Git**

---

## Setup

```powershell
# From the repository root
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip wheel

# Install all project deps (top-level + module-specific)
pip install -r .\requirements.txt `
  -r .\src\vast\gateway\requirements.txt `
  -r .\src\vast\runner\requirements.txt `
  -r .\src\vast\orthophoto_canvas\requirements.txt

# Ensure binary wheels for these heavy packages (avoids build issues)
pip install --only-binary=:all: PyQt6 PyQt6-WebEngine grpcio grpcio-tools


## Running (4 terminals)
#Start Grafana/Prometheus (optional but recommended for the demo
docker compose up -d prometheus grafana
docker compose ps

## Terminal A - Runner (gRPC → SQLite)
.\.venv\Scripts\Activate.ps1
$env:SQLITE_DB = "/C:/Users/sara/Documents/login-and-gui/data/app.db"
python -m vast.runner.runner_server

## Terminal B – Gateway (FastAPI)
.\.venv\Scripts\Activate.ps1
python -m uvicorn vast.gateway.app:create_app --factory --host 127.0.0.1 --port 9001

## Terminal C - Demo metrics exporter (Flask)
.\.venv\Scripts\Activate.ps1
python -m vast.services.sensors_metrics_app

## Terminal D - Desktop app (PyQt6)
.\.venv\Scripts\Activate.ps1
$env:GATEWAY_URL = "http://127.0.0.1:9001"
python .\src\vast\main.py

