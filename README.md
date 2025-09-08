# AgCloud

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

Terminal A:
.\.venv\Scripts\Activate.ps1
$env:SQLITE_DB = "/C:/Users/sara/Documents/login-and-gui/data/app.db"
python -m runner.runner_server

Terminal B:
.\.venv\Scripts\Activate.ps1
python -m uvicorn gateway.app:create_app --factory --host 127.0.0.1 --port 9001

Terminal C:
.\.venv\Scripts\Activate.ps1
python -m services.sensors_metrics_app

Terminal D:
.\.venv\Scripts\Activate.ps1
$env:GATEWAY_URL = "http://127.0.0.1:9001"
python .\main.py
