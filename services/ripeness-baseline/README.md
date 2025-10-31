# 🍏 Fruit Ripeness Baseline System

## Overview

This service implements a **baseline system for tracking fruit ripeness** using simple color and texture heuristics.  
It processes sample fruit images, generates weekly rollups, and stores results in PostgreSQL.  
Quality flags are added to highlight questionable or low-confidence cases.

---

## Features

- **Ripeness Heuristics:**  
  Uses HSV color space and texture analysis (Laplacian variance) to estimate fruit ripeness (Unripe, Ripe, Overripe).
- **Image Processing Pipeline:**  
  Processes sample fruit images, extracts relevant features, and classifies ripeness.
- **Weekly Rollups:**  
  Aggregates ripeness data weekly and exports results to a relational database.
- **Quality Flags:**  
  Flags low-confidence or outlier results for further review.

---

## Project Structure

- `src/` – Python pipeline (heuristics, quality flags, DB inserts)
- `deploy/sql/` – Database schema, rollup queries, and view definitions
- `README.md` – Documentation

---

## How to Run

### 1. Prerequisites

- **Docker & Docker Compose** installed  
- Access to the shared **RelDB stack** (`db` service must be running)  
- Clone this repository into your workspace

### 2. Build the Docker Image

```bash
docker build --no-cache -t ripeness-baseline:local -f deploy/Dockerfile .
```

### 3. Run the Pipeline

Connect the container to the same Docker network as the database (`reldb_airnet`):

```powershell
docker run --rm --network agcloud-net `
  -e PGHOST=db -e PGPORT=5432 -e PGDATABASE=missions_db `
  -e PGUSER=missions_user -e PGPASSWORD="pg123" `
  -e LOOKBACK_DAYS=7 `
  -e MINIO_URL="http://minio-hot-1:9000" `
  -e MINIO_ACCESS_KEY=minioadmin -e MINIO_SECRET_KEY=minioadmin123 `
  ripeness-baseline:local
```

At the end, you will see:
```
Done. Inserted detections and updated weekly_rollups.
```

---

## Useful Commands (PowerShell)

### View Results Per Image (Full History)

```powershell
docker exec -e PGPASSWORD="pg123" -it db `
  psql -U missions_user -d missions_db -c `
"SELECT d.detection_id,
        i.source_path,
        d.ripeness,
        d.quality_flags,
        to_char(d.created_at,'YYYY-MM-DD HH24:MI:SS') AS created_at
   FROM detections d
   JOIN images i USING (image_id)
  ORDER BY d.created_at DESC;"
```

### View Weekly Summaries (View Table)

```powershell
docker exec -e PGPASSWORD="pg123" -it db `
  psql -U missions_user -d missions_db -c `
"SELECT * FROM v_weekly_ripeness ORDER BY iso_year, iso_week;"
```

### Run Evaluation Script for All Fruit Types...

```powershell
# Apple
python .\src\evaluate_minio.py --minio-url http://127.0.0.1:9001 `
  --access-key minioadmin --secret-key minioadmin123 `
  --bucket imagery --prefix apple/test --fruit apple `
  --thresholds-json .\thresholds.apple.json `
  --outdir .\eval\apple_test

# Banana
python .\src\evaluate_minio.py --minio-url http://127.0.0.1:9001 `
  --access-key minioadmin --secret-key minioadmin123 `
  --bucket imagery --prefix banana/test --fruit banana `
  --thresholds-json .\thresholds.banana.json `
  --outdir .\eval\banana_test

# Orange
python .\src\evaluate_minio.py --minio-url http://127.0.0.1:9001 `
  --access-key minioadmin --secret-key minioadmin123 `
  --bucket imagery --prefix orange/test --fruit orange `
  --thresholds-json .\thresholds.orange.json `
  --outdir .\eval\orange_test


```
---

## How It Works

1. **Define Heuristics:**  
   Ripeness is determined by average hue, saturation, value, texture variance, and brown/dark pixel ratio.

2. **Process Images:**  
   Images are segmented and analyzed. Features are extracted and ripeness is classified.

3. **Weekly Rollups:**  
   Results are aggregated by week and stored in the database.

4. **Quality Flags:**  
   Results with low confidence or outlier features are flagged for review.

---

## Notes

- You can change the fruit type (`FRUIT_TYPE`) or green leaf flag threshold (`GREEN_LEAF_FLAG_THR`) as needed.
- Weekly rollups aggregate detections by `(fruit_type, iso_year, iso_week)`.
- Each result includes quality flags (bitmask) and ripeness classification.
- Weekly summaries are updated automatically at the end of each run.

---

## Additional Info

- Thresholds and heuristics can be adjusted in `src/heuristics.py` for different fruit types or conditions.
- For advanced deployment, see `deploy/k8s-cronjob.yaml` for Kubernetes.