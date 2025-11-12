#!/usr/bin/env bash
set -euo pipefail
cd "${AIRFLOW_HOME}/services/ripeness"
docker compose up --build --abort-on-container-exit --exit-code-from ripeness
