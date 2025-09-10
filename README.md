# AgCloud-Sounds

## AgCloud – MQTT → Kafka Bridge

This project sets up a Docker Compose environment with:

- Mosquitto (MQTT broker)

- Kafka (Bitnami KRaft, single broker, no replication)

- Kafka Connect with an MQTT Source Connector

- A PowerShell script (agcloud_bench.ps1) for automated testing, publishing, and latency benchmarks

### How to Run

**Note:** At the end of this document you will also find a **one-liner command** that runs the entire setup (services + live subscribers + interactive send) in a single step.

#### Setup

go to project root

```powershell
cd <project-root>
```

exp.

```powershell
cd C:\Users\user1\Desktop\AgCloud\AgCloud
```

Start the environment (Mosquitto + Kafka + Connect):

```powershell
.\agcloud_bench.ps1 up
```

This builds and runs all required containers.

#### MQTT ↔ Kafka Connector

Two connector configs are included:

- mqtt-fast.json – maps mqtt/latency → raw.mqtt.fast

- mqtt-source.json – maps mqtt/# → raw.mqtt.in

Apply connector config:

```powershell
docker compose exec -T connect curl -s -X PUT -H "Content-Type: application/json" --data "@mqtt-fast.json" http://localhost:8083/connectors/mqtt-fast/config
```

Restart connector:

```powershell
docker compose exec -T connect curl -s -X POST http://localhost:8083/connectors/mqtt-fast/restart
```

Check status:

```powershell
docker compose exec -T connect curl -s http://localhost:8083/connectors/mqtt-fast/status
```

#### Bench Script

##### Live subscribers

Opens two windows – one with MQTT mosquitto_sub, one with Kafka tail:

```powershell
.\agcloud_bench.ps1 live
```

##### Send messages interactively

Allows typing JSON to publish:

```powershell
.\agcloud_bench.ps1 send
```

Example:

```powershell
{"user":"user1","action":"test"}
```

##### Latency benchmark

Publish 1000 messages and measure:

```powershell
.\agcloud_bench.ps1 bench -Count 1000
```

#### Quick test with kcat

Consume from Kafka directly:

```powershell
docker run -it --rm --network agcloud_mesh edenhill/kcat:1.7.1 `
  -b kafka:9092 -C -t raw.mqtt.fast -o end -q -f "%s\n"
```

#### One-liner command

For a full run (start environment, open live windows, enter interactive send):

```powershell
powershell -NoExit -Command "Set-ExecutionPolicy -Scope Process Bypass; .\agcloud_bench.ps1 up; .\agcloud_bench.ps1 live; .\agcloud_bench.ps1 send"
```

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

This project provides a CLI tool that replays telemetry and sensor payloads from **CSV/Parquet** files at a fixed **QPS** to **MQTT** and/or **Kafka**.  
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
python data_simulator.py --qps 100 --duration 30 --out both --file data/sample.csv --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic telemetry   --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
```

#### 2 MQTT only

```bash
python data_simulator.py --qps 5 --duration 10 --out mqtt --file data/sample.csv   --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic telemetry
```

#### 3 Kafka only

```bash
python data_simulator.py --qps 5 --duration 10 --out kafka --file data/sample.csv --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
```

#### 4 Stability profile (60s @ 1k msg/s)

```bash
python data_simulator.py --stability --out kafka --file data/sample.csv --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
```

#### 5 Performance profile (15m @ 10k msg/s)

> Parquet is recommended for faster reads:

```python
import pandas as pd; pd.read_csv("sample.csv").to_parquet("sample.parquet")
```

```bash
python data_simulator.py --perf --out kafka --file data/sample.parquet --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
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
  Optional. Kafka topic name. Default: `dev-robot-telemetry-raw`.

### Example Output

After running a short test:

```bash
python data_simulator.py --qps 5 --duration 5 --out both --file data/sample.csv --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic telemetry --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
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
- Load: 150s @ 1000 msg/s to MQTT topic `soak/test`, consumed from Kafka topic `dev-robot-telemetry-raw`.
- Results: Check "MQTT to Kafka Soak Test Results" and download artifacts (logs, junit.xml, bridge.json).
- Pass/Fail: Job fails if loss_pct > 1.0%.
