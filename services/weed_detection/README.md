# 🌱 Weed Detection Pipeline — MinIO → PostgreSQL

## Overview
This project implements a **weed detection and analysis pipeline** that automatically:
1. Retrieves images from **MinIO** (S3-compatible object storage).  
2. Runs **weed detection** using a combination of heuristic image analysis and machine learning (MobileNetV3).  
3. Writes detection results and statistics into a **Relational Database (PostgreSQL)**.  

It’s designed for **automated weekly or on-demand runs** using Docker or local Python execution.

---

## 🧠 Architecture

**Flow:**  
`MinIO (images) → Local cache → Weed Detection (Heuristic + ML) → PostgreSQL`

### Main Steps
1. **Data Input**  
   - Images are loaded from MinIO using the credentials defined in `.env`.  
   - Supports both local and remote (S3-compatible) backends.  

2. **Processing**  
   - **Heuristic Detection** using Excess Green (ExG) and Otsu thresholding.  
   - **ML Refinement** with a small MobileNetV3 model (`ml_model.py`) to improve detection accuracy.  
   - Output: weed masks, bounding boxes, and anomaly scores.  

3. **Database Output**  
   - Results are inserted into PostgreSQL tables (`tile_stats`, `anomalies`, `qa_runs`) via SQLAlchemy.  
   - Geometry data is stored as WKT (PostGIS-compatible).  

---

## 🧩 Project Structure

```
project_root/
├── scripts/
│   └── run_detection.py      # Main entry point for batch processing
├── src/
│   ├── detectors/            # Weed and disease detection logic
│   ├── pipeline/             # Database and utility modules
│   └── models/               # ML models (e.g., MobileNetV3)
├── data/                     # Local image cache
├── Dockerfile
├── docker-compose.yml
├── .env
└── run_weekly.ps1            # Windows PowerShell automation script
```

---

## ⚙️ Technologies Used

| Component        | Description |
|------------------|-------------|
| **Python 3.10+** | Core language |
| **PyTorch**      | ML inference (MobileNetV3) |
| **OpenCV**       | Image preprocessing and segmentation |
| **SQLAlchemy**   | ORM and database connection |
| **MinIO SDK**    | S3-compatible data access |
| **Docker Compose** | Service orchestration |
| **PostgreSQL + PostGIS** | Result storage and spatial data handling |

---

## 🧾 Environment Configuration

The `.env` file defines all key environment variables:
```ini
DB_URL=postgresql+psycopg2://user:password@db:5432/missions_db
STORAGE_BACKEND=minio
MINIO_ENDPOINT=minio-hot:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=ground
MINIO_SECURE=false
BATCH_SIZE=64
MAX_WORKERS=4
MIN_BBOX_AREA=150
MIN_COMPONENT_AREA=200
```

---

## 🚀 Running the Project

### Option 1: Run via Docker
```bash
docker compose up -d --build
docker compose logs -f weed-detector
```

### Option 2: Run Locally (Python)
```bash
python -m venv .venv
source .venv/bin/activate       # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m scripts.run_detection --storage minio
```

---

## 🕒 Scheduled Execution (Windows)

The `run_weekly.ps1` script automates weekly runs using **Task Scheduler**.  
It:
- Ensures Docker is running  
- Executes `docker compose run` for the detector  
- Logs output to `C:\logs\weed-weekly.log`  
- Prevents concurrent runs using a lock mechanism  

---

## 🗄️ Database Schema (Simplified)

| Table         | Purpose |
|----------------|----------|
| **anomalies**  | Stores detected weed events and metadata |
| **tile_stats** | Aggregated scores per image/tile |
| **qa_runs**    | Logs of detection runs for debugging and QA |

> Requires PostgreSQL with PostGIS enabled for geometry operations.

---

## 🧰 Troubleshooting

| Issue | Cause | Fix |
|-------|--------|-----|
| **Torch model not found** | blocked download or cache missing | Manually place model in `~/.cache/torch/hub/checkpoints` |
| **UniqueViolation on tile_stats** | duplicate tile_id/mission_id | Add `ON CONFLICT DO NOTHING` or adjust mission IDs |
| **Slow performance** | batch size too high | Lower `BATCH_SIZE` and `MAX_WORKERS` |
| **SSL errors** | missing CA certificate | Verify `CA_CERT_PATH` or disable `MINIO_SECURE` if local |

---

## 🏁 Summary

This project provides an **end-to-end pipeline** for automated weed detection — from image retrieval to database integration — built for scalable, repeatable, and containerized deployment.
