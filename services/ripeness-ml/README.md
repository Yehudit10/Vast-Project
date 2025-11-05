# Ripeness ML – API & Weekly Job

A small **FastAPI** service that:
- Predicts fruit ripeness (**ripe / unripe / overripe**) for new images from **MinIO** based on the trained conditional model, and writes results to **Postgres**.
- Creates a **weekly rollup snapshot** (with TS window) per fruit.

---

## 🧩 Repo layout (service)

```
services/ripeness-ml/
├─ scripts/
│  ├─ ripeness_api.py           # FastAPI endpoints (predict + rollup)
│  └─ weekly_ripeness_job.py    # model/minio/db helpers reused by the API
├─ checkpoints/
│  └─ mobilenet_v3_large/
│     └─ best_conditional.pt    # your trained model weights (mounted into /models)
├─ Dockerfile
├─ docker-compose.ripeness.yml
├─ requirements.txt
└─ .env (optional)
```

---

## ⚙️ Requirements

- Docker Desktop  
- External Docker network: **agcloud_ag_cloud** (same as your existing stack)

**Running services on that network:**
- Postgres (`postgres:5432`, DB: `missions_db`, user: `missions_user`)
- MinIO (`minio-hot:9000`)

---

## 🌍 Environment variables

Set via `docker-compose.ripeness.yml` or `.env`:

| Name | Default | Notes |
|------|----------|-------|
| `PGHOST` | postgres | DB host (inside Docker network) |
| `PGPORT` | 5432 |  |
| `PGDATABASE` | missions_db |  |
| `PGUSER` | missions_user |  |
| `PGPASSWORD` | pg123 |  |
| `MINIO_ENDPOINT` | minio-hot:9000 | S3 API port is 9000 inside Docker |
| `MINIO_SECURE` | false | set true if TLS to MinIO |
| `MINIO_ACCESS_KEY` | minioadmin |  |
| `MINIO_SECRET_KEY` | minioadmin |  |
| `MODEL_PATH` | /models/best_conditional.pt | mounted from host |
| `MODEL_NAME` | best_conditional | stored in DB |
| `BATCH_LIMIT` | 500 | safety cap per run |
| `FRUITS` (optional) | Apple,Orange,Grape,Strawberry | if enabled in code |

If you’re behind **NetFree/proxy**, copy your CA file to `deploy/certs/` and use the Dockerfile section that installs CA + `update-ca-certificates`.

---

## 🐳 Build & Run (Docker)

From `services/ripeness-ml/`:

```bash
docker compose -f docker-compose.ripeness.yml build ripeness-api
docker compose -f docker-compose.ripeness.yml up -d ripeness-api
```

**Health check:**

```bash
curl http://localhost:8088/healthz
```

# **logs**
```bash
docker logs -n 200 ripeness-api
```

---

## 🔌 API

**Base URL:** `http://localhost:8088`

### POST `/predict-last-week`
Runs prediction for images from the last 7 days that don’t have a record yet in `ripeness_predictions`.

```bash
curl -X POST http://localhost:8088/predict-last-week
# -> {"processed": 17}
```

### POST `/predict-batch`
Run for a custom time window and limit.

**Request body (JSON):**
```json
{
  "since_ts": "2025-10-01T00:00:00",
  "limit": 1000
}
```

**Example:**
```bash
curl -X POST http://localhost:8088/predict-batch -H "Content-Type: application/json" -d '{"since_ts":"2025-10-01T00:00:00","limit":1000}'
```

### POST `/rollup/weekly`
Creates a weekly snapshot into `ripeness_weekly_rollups_ts` for the last 7 days (creates the table if missing).

```bash
curl -X POST http://localhost:8088/rollup/weekly
# -> {"ok": true}
```

---

## 🧮 Database schema

### Predictions table
```sql
CREATE TABLE IF NOT EXISTS ripeness_predictions (
  id BIGSERIAL PRIMARY KEY,
  inference_log_id BIGINT NOT NULL REFERENCES inference_logs(id) ON DELETE CASCADE,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(),
  ripeness_label TEXT NOT NULL CHECK (ripeness_label IN ('ripe','unripe','overripe')),
  ripeness_score DOUBLE PRECISION NOT NULL,
  model_name TEXT NOT NULL,
  UNIQUE (inference_log_id)
);
```

### Weekly rollups
```sql
CREATE TABLE IF NOT EXISTS ripeness_weekly_rollups_ts (
  id BIGSERIAL PRIMARY KEY,
  ts TIMESTAMPTZ NOT NULL DEFAULT now(), -- snapshot time
  window_start TIMESTAMPTZ NOT NULL,
  window_end TIMESTAMPTZ NOT NULL,
  fruit_type TEXT NOT NULL,
  cnt_total INTEGER NOT NULL,
  cnt_ripe INTEGER NOT NULL,
  cnt_unripe INTEGER NOT NULL,
  cnt_overripe INTEGER NOT NULL,
  pct_ripe DOUBLE PRECISION NOT NULL
);
```

---

## 🔍 Useful queries

**Show latest predictions joined with inference logs:**
```sql
SELECT il.id, il.fruit_type, il.image_url, rp.ripeness_label, rp.ripeness_score, rp.model_name, rp.ts
FROM inference_logs il
JOIN ripeness_predictions rp ON rp.inference_log_id = il.id
ORDER BY rp.ts DESC
LIMIT 20;
```

**Show rollup snapshots:**
```sql
SELECT ts::date AS snapshot_day, fruit_type, cnt_total,
cnt_ripe, cnt_unripe, cnt_overripe,
ROUND(pct_ripe*100,2) AS pct_ripe_pct
FROM ripeness_weekly_rollups_ts
ORDER BY ts DESC, fruit_type;
```

**From Docker (network agcloud_ag_cloud):**
```bash
docker run --rm --network agcloud_ag_cloud -e PGPASSWORD=pg123 postgres:16-alpine   psql -h postgres -U missions_user -d missions_db -c   "SELECT ts::date AS snapshot_day, fruit_type, cnt_total, cnt_ripe, cnt_unripe, cnt_overripe, ROUND(pct_ripe*100,2) AS pct_ripe_pct
   FROM ripeness_weekly_rollups_ts
   ORDER BY ts DESC, fruit_type;"
```

---

## 🕒 Scheduling (Windows Task Scheduler)

Create a weekly job that first predicts, then rolls up.

**run_weekly.ps1:**
```powershell
Invoke-RestMethod -Method Post -Uri "http://localhost:8088/predict-last-week"
# note: /predict-last-week now triggers the weekly rollup automatically,
# so a single call is sufficient (no duplicate predictions are inserted).
```

**Register task:**
```bash
schtasks /Create /TN "RipenessWeekly" /TR "powershell.exe -ExecutionPolicy Bypass -File C:\path\run_weekly.ps1" /SC WEEKLY /D MON /ST 03:00
```

---

## 🧰 Troubleshooting

- **MinIO errors / 9000 vs 9001:** inside Docker network always use `minio-hot:9000` (S3 API).  
  Ports 9001/9002 are host-exposed console/proxy.
- **SignatureDoesNotMatch:** wrong `MINIO_ACCESS_KEY`/`SECRET_KEY` or endpoint (should be the S3 API).
- **Model FRUITS mismatch:** ensure the FRUITS list in code matches the model checkpoint (e.g. include Grape if trained).
- **SSL to PyPI (NetFree/proxy):** add your CA to the image and run `update-ca-certificates`.
- **No rows processed:** endpoint processes only inference logs without an existing prediction; expand window with `/predict-batch`.

---

## 👩‍💻 Maintainer

**Name:** Ayala  
**Service name:** ripeness-api  
**Ports:** 8088/tcp
