# MQTT → MinIO Hot/Cold Ingest (with ILM Tiering)

This project sets up a local development environment for an MQTT → MinIO (Hot) pipeline  
with automatic tiering to MinIO (Cold). It includes automatic ILM bootstrap,  
a sample publisher, and monitoring (Prometheus/Grafana).

---

## Prerequisites
- Docker + Docker Compose installed
- Open ports:
  - `1883` (MQTT broker)
  - `9000/9001` (MinIO Hot server + console)
  - `9100/9101` (MinIO Cold server + console)
  - `3000` (Grafana)
  - `9090` (Prometheus)

---

## Quick Start

```bash
docker compose up -d --build
```

Default credentials:
- `MINIO_ROOT_USER=minioadmin`
- `MINIO_ROOT_PASSWORD=minioadmin123`

---

## Services

- **MinIO Hot Console:**   http://localhost:9002  
- **MinIO Cold Console:**  http://localhost:9102 
- **MQTT Broker:**         tcp://localhost:1883  
- **Grafana Dashboard:**   http://localhost:3000  
- **Prometheus Metrics:**  http://localhost:9090  

---

## What the bootstrap (`init.sh`) does

- Configures `mc` aliases for Hot/Cold
- Ensures buckets `imagery` and `telemetry` exist
- Enables Versioning on those buckets
- Creates remote tiers: `COLD_IMAGERY`, `COLD_TELEMETRY`
- Applies default ILM (7 days → Cold)

---

## Quick Checks

List buckets and tiers:
```bash
docker compose exec mc-bootstrap sh -lc 'mc ls hot && mc admin tier ls hot'
```

Check ILM:
```bash
docker compose exec mc-bootstrap sh -lc 'mc ilm ls hot/imagery && mc ilm ls hot/telemetry'
```

Upload a test file:
```bash
docker compose exec mc-bootstrap sh -lc 'echo "hello" > /tmp/test.txt && mc cp /tmp/test.txt hot/imagery/'
```

Check file status:
```bash
docker compose exec mc-bootstrap sh -lc 'mc stat hot/imagery/test.txt'
```

---


## Reset Rules

```bash
docker compose exec mc-bootstrap sh -lc '
for b in imagery telemetry; do
  ids=$(mc ilm export hot/$b 2>/dev/null | sed -n "s/.*\"ID\" *: *\"\([^\"]\+\)\".*/\1/p" || true)
  for id in $ids; do mc ilm rule rm hot/$b --id "$id" || true; done
done
'
docker compose restart mc-bootstrap
```

---

## Troubleshooting

- **"Invalid credentials"** → check `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`
- **File remains STANDARD** → wait or verify ILM is set to 0 days
