# AgCloud-Sounds

## AgCloud – End-to-End MQTT → Kafka (Quickstart)

This guide shows how to:
make the MQTT connector plugin available to Kafka Connect,
run the end-to-end test with full logs,
publish a test MQTT message and verify it lands in Kafka.
Works on Windows (PowerShell) with WSL, or on Linux/Git Bash.

### Prerequisites

Docker Desktop + Compose
WSL (Windows) or any Bash shell
Images will be pulled automatically on first run.
Project layout (relevant bits):
connect/plugins/confluentinc-kafka-connect-mqtt-1.7.6/...
connectors/mqtt-source.json     # maps mqtt/#  -> raw.mqtt.in
run_all.sh
docker-compose.yml

### Make the MQTT Connector plugin available

#### Permanent (recommended): Compose volume mapping

Bring up the stack:

```PowerShell
docker compose up -d connect
```

Check that the plugin is registered:

```PowerShell
curl -s http://localhost:8083/connector-plugins | Select-String mqtt
```

Expected output includes:

```PowerShell
"io.confluent.connect.mqtt.MqttSourceConnector"
```

### Run the full E2E flow with logs

This runs the whole stack, waits for health, ensures the connector, publishes a test message, and consumes from Kafka.
It also saves a timestamped log file and keeps the window open so you can read errors.

#### Windows PowerShell

```PowerShell
wsl bash -lc 'set -x; ./run_all.sh 2>&1 | tee run_all.$(date +%Y%m%d_%H%M%S).log; read -rp "Press Enter to close..." _'
```

#### Linux / Git Bash

```PowerShell
bash -x ./run_all.sh 2>&1 | tee run_all.$(date +%Y%m%d_%H%M%S).log
```

You should see lines like:
==> Checking connector plugins ...
MQTT plugin detected.
...
mqtt-source is RUNNING.
==> Publishing test MQTT message ...
==> Consuming from Kafka (kcat) ...
If it hangs on “Consuming from Kafka (kcat) …”, publish a message (next step).

### Publish a test MQTT message (in a second window)

Open another terminal and run:

```PowerShell
docker exec -it mosquitto \
  mosquitto_pub -h mosquitto -p 1883 -t mqtt/test -m '{"hello":"world"}'
```

Go back to the first window and confirm a record was consumed.

### Clean up

```PowerShell
docker compose down -v
```

This stops and removes containers, network, and volumes.

## Kafka Single – Kafka in Docker

This project provides a simple Dockerfile to run Kafka (Bitnami image, single broker with topics and smoke test).

### Run Instructions

Run the project with the following commands:

```bash
docker build -t kafka-single:local .

docker run -d --name kafka-single -p 29092:9094 -p 9092:9092 --env-file .\kafka-files\kafka.env.example kafka-single:local 

docker logs --tail 200 kafka-single

docker rm -f kafka-single
```

### Notes - kafka

- The first command builds the image.

- The second command runs the container.

- The third command shows the logs – wait a few minutes before running it. If you don’t see ✅ or ❌, run the command again.

- The fourth command removes the container.
If the container is running and you want to reset it, use this command.

## AgCloud - Data Simulator

This project provides a CLI tool that replays sound and sensor payloads from **CSV/Parquet** files at a fixed **QPS** to **MQTT** and/or **Kafka**.  
It is used to validate throughput, stability, and reliability of the messaging stack.

### Features

- Publish messages to **MQTT**, **Kafka**, or both.
- Input from **CSV** or **Parquet** (Parquet recommended for high QPS).
- Metrics: sent / acked / lost, latency (p50/p95/p99), jitter.
- Stability profile: 60s @ 1k msg/s.
- Performance profile: 15m @ 10k msg/s.
- KPI: message loss ≤ **0.5%**.

### Install

```bash
python -m venv .venv && source .venv/bin/activate    
pip install -r requirements.txt
```

### Quick Examples

#### 1 Publish to both (MQTT + Kafka)

```bash
python data_simulator.py --qps 100 --duration 30 --out both --file data/sample.csv --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic sound   --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-sound-raw
```

#### 2 MQTT only

```bash
python data_simulator.py --qps 5 --duration 10 --out mqtt --file data/sample.csv   --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic sound
```

#### 3 Kafka only

```bash
python data_simulator.py --qps 5 --duration 10 --out kafka --file data/sample.csv --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-sound-raw
```

#### 4 Stability profile (60s @ 1k msg/s)

```bash
python data_simulator.py --stability --out kafka --file data/sample.csv --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-sound-raw
```

#### 5 Performance profile (15m @ 10k msg/s)

> Parquet is recommended for faster reads:

```python
import pandas as pd; pd.read_csv("sample.csv").to_parquet("sample.parquet")
```

```bash
python data_simulator.py --perf --out kafka --file data/sample.parquet --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-sound-raw
```

### Simulator CLI options

- `--file <PATH>`  
  **Required**. Path to input CSV file. Must exist under `data/` (e.g. `data/sample.csv`).

- `--qps <FLOAT>`  
  Optional. Messages per second to produce. Default: `1.0`.

- `--duration <SEC>`  
  Optional. How long to run (in seconds). Default: `10`.

- `--out <kafka|mqtt|both>`  
  Optional. Where to send the records. Default: `kafka`.

- `--loop`  
  Optional flag (no value). If set, replay file in a loop. Default: disabled.

- `--bootstrap <BROKERS>`  
  Optional. Kafka bootstrap servers. Default: `localhost:29092`.

- `--topic <NAME>`  
  Optional. Kafka topic name. Default: `dev-robot-sound-raw`.

### Example Output

After running a short test:

```bash
python data_simulator.py --qps 5 --duration 5 --out both --file data/sample.csv --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic sound --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-sound-raw
```

You may see a summary like:

```bash
[summary]
  total: sent=5 runtime=1.81s qps_avg≈2.76
  jitter (std of inter-arrival): 0.000782s
  kafka: sent=5 acked=5 lost=0 p50/p95/p99=201.0ms/561.9ms/594.1ms
  mqtt : sent=5 acked=5 lost=0 p50/p95/p99=3.8ms/5.3ms/5.5ms
  kafka loss: 0.000%
  mqtt  loss: 0.000%
```

### Notes - data simulator

- KPI target: **loss ≤ 0.5%** (PASS).
- CSV/Parquet input is required (`--file`). Install `pyarrow` or `fastparquet` for Parquet.
- Make sure your brokers are reachable (e.g., Mosquitto on 1883; Kafka advertised at 9094).

## MQTT→Kafka Soak (Docker Compose)

- Trigger: Actions → "Soak Test (MQTT to Kafka Bridge)" → Run workflow.
- Load: 150s @ 1000 msg/s to MQTT topic `soak/test`, consumed from Kafka topic `dev-robot-sound-raw`.
- Results: Check "MQTT to Kafka Soak Test Results" and download artifacts (logs, junit.xml, bridge.json).
- Pass/Fail: Job fails if loss_pct > 1.0%.
