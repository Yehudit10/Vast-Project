# AgCloud-Sounds

## AgCloud – Kafka on KinD

This project demonstrates how to deploy Kafka on KinD using the Bitnami Helm chart, configure topics with 7-day retention, and verify the setup with a smoke test using kcat.

### Prerequisites

- Docker Desktop installed and running

- Internet access for pulling images and charts

- Git (for cloning and versioning)

Files in this repo:

- Dockerfile – container with kubectl, kind, and helm

- values-kafka.yaml – Helm values for Kafka (single broker, auto topic creation disabled)

- create-topics.sh – script that creates topics with 7-day retention

- .gitattributes – ensures LF line endings for scripts

- .dockerignore – ignores irrelevant files during Docker build

### Build and Run

#### 1. Build the image

```bash
cd kafka-kind
docker build -t kafka-kind:local .
```

#### 2. Start KinD + Kafka

Run the container and mount the YAML and topic script. This will:

- Create a KinD cluster

- Deploy Kafka with Helm

- Copy and run create-topics.sh inside the broker pod

- Expose Kafka at localhost:29092

Linux / macOS (bash):

```bash
docker run --privileged --rm -it \
  -v "$PWD/values-kafka.yaml:/work/values-kafka.yaml:ro" \
  -v "$PWD/create-topics.sh:/work/create-topics.sh:ro" \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -p 29092:29092 \
  kafka-kind:local
```

Windows (PowerShell):

```powershell
    docker run --privileged --rm -it `
    -v "${PWD}\values-kafka.yaml:/work/values-kafka.yaml:ro" `
    -v "${PWD}\create-topics.sh:/work/create-topics.sh:ro" `
    -v //var/run/docker.sock:/var/run/docker.sock `
    -p 29092:29092 `
    kafka-kind:local
```

At the end you should see:

Kafka reachable at: localhost:29092

### Smoke Test with kcat

#### 1. Create kcat pod

```bash
kubectl --kubeconfig $kc run kcat \
  --restart=Never \
  --image=docker.io/edenhill/kcat:1.7.1 \
  --image-pull-policy=IfNotPresent \
  --command -- /bin/sh -c "while true; do sleep 3600; done"
```

Wait until the pod is ready:

```bash
kubectl --kubeconfig $kc wait pod/kcat --for=condition=Ready --timeout=180s
```

#### 2. Produce a message

```bash
kubectl --kubeconfig $kc exec -it kcat -- sh -lc \
  "echo 'smoke-test' | kcat -P -b kafka.default.svc.cluster.local:9092 -t dev-robot-alerts -v"
```

#### 3. Consume a message

```bash
kubectl --kubeconfig $kc exec -it kcat -- sh -lc \
  "kcat -C -b kafka.default.svc.cluster.local:9092 -t dev-robot-alerts -o -1 -c 1 -q"
```

If you see smoke-test printed back, the setup works.

#### Notes

- Deployment uses 1 controller and 1 broker (no replication).

- Auto topic creation is disabled — topics are explicitly created via create-topics.sh.

- All topics have 7-day retention by default.

- Kafka is exposed at localhost:29092 for producers/consumers outside the cluster.

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
python -m venv .venv && source .venv/bin/activate    # (Windows PowerShell: .venv\Scripts\Activate.ps1)
pip install -r requirements.txt
```

### Quick Examples

#### 1) Publish to both (MQTT + Kafka)
```bash
python data_simulator.py --qps 100 --duration 30 --out both --file data/sample.csv   --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic telemetry   --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
```

#### 2) MQTT only
```bash
python data_simulator.py --qps 5 --duration 10 --out mqtt --file data/sample.csv   --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic telemetry
```

#### 3) Kafka only
```bash
python data_simulator.py --qps 5 --duration 10 --out kafka --file data/sample.csv   --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
```

#### 4) Stability profile (60s @ 1k msg/s)
```bash
python data_simulator.py --stability --out kafka --file data/sample.csv   --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
```

#### 5) Performance profile (15m @ 10k msg/s)
> Parquet is recommended for faster reads:
```python
import pandas as pd; pd.read_csv("sample.csv").to_parquet("sample.parquet")
```
```bash
python data_simulator.py --perf --out kafka --file data/sample.parquet   --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
```

### Example Output

After running a short test:

```bash
python data_simulator.py --qps 5 --duration 5 --out both --file datasample.csv --mqtt-host 127.0.0.1 --mqtt-port 1883 --mqtt-topic telemetry --kafka-bootstrap localhost:29092 --kafka-topic dev-robot-telemetry-raw
```

You may see a summary like:
```
[summary]
  total: sent=5 runtime=1.00s qps_avg≈5.00
  jitter (std of inter-arrival): 0.000179s
  kafka: sent=5 acked=5 lost=0 p50/p95/p99=n/a/n/a/n/a
  mqtt : sent=5 acked=5 lost=0 p50/p95/p99=0.0ms/0.1ms/0.1ms
  kafka loss: 0.000%
  mqtt  loss: 0.000%
```

### Notes
- KPI target: **loss ≤ 0.5%** (PASS).
- CSV/Parquet input is required (`--file`). Install `pyarrow` or `fastparquet` for Parquet.
- Make sure your brokers are reachable (e.g., Mosquitto on 1883; Kafka advertised at 9094).

