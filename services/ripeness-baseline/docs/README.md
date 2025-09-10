# Fruit Ripeness Baseline System

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
- `samples/` – Place your fruit images here (JPG/PNG/WebP)
- `deploy/sql/` – Database schema, rollup queries, and view definitions
- `docs/README.md` – Documentation

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

```bash
docker run --rm --network reldb_airnet \
  -e PGHOST=db -e PGPORT=5432 \
  -e PGDATABASE=missions_db \
  -e PGUSER=missions_user \
  -e PGPASSWORD="Missions!ChangeMe123" \
  ripeness-baseline:local
```

If successful, you should see:
```
Done. Inserted detections and updated weekly_rollups.
```

### 4. Verify Results in PostgreSQL

Check the weekly rollups table:

```bash
docker exec -e PGPASSWORD="Missions!ChangeMe123" -it db \
  psql -U missions_user -d missions_db -c "SELECT * FROM weekly_rollups ORDER BY iso_year, iso_week;"
```

Or use the convenient view:

```bash
docker exec -e PGPASSWORD="Missions!ChangeMe123" -it db \
  psql -U missions_user -d missions_db -c "SELECT * FROM v_weekly_ripeness ORDER BY iso_year, iso_week;"
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

- Add your images under `samples/` before running the container.
- Weekly rollups aggregate detections by `(fruit_type, iso_year, iso_week)`.
- Quality flags (e.g., green-leaf detection, low-confidence) are automatically set during processing.

---

## Additional Info

- Thresholds and heuristics can be adjusted in `src/heuristics.py` for different fruit types or conditions.
- For advanced deployment, see `deploy/k8s-cronjob.yaml` for Kubernetes