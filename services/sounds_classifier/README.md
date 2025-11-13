# 🎧 Sound Classifier Service (CNN14-based)

Service that classifies audio files using CNN14 model. It:
1. Receives S3 object location (bucket+key)
2. Classifies the sound
3. Stores result in PostgreSQL (optional)
4. Sends alert to Kafka topic if specific sounds detected (optional)
Built with **FastAPI**, **PANNs (CNN14)**, **PostgreSQL**, and optional **Kafka alerts** for real-time monitoring.

## Quick Start
```bash
docker compose up -d sounds_classifier
```
Service runs on **http://localhost:8088** (see `docker-compose.yml`, port 8088).

## API Usage
```json
POST /classify
{
    "s3_bucket": "your-bucket",
    "s3_key": "path/to/audio.wav"
}
```

### Example Response
```json
{
  "label": "vehicle",
  "probs": {
    "vehicle": 0.93,
    "animal": 0.05,
    "shotgun": 0.02
  }
}
```

## Supported Audio Formats
- WAV, MP3, FLAC, OGG
- M4A, AAC, WMA, OPUS


## Health & Docs
- `GET /health` → basic readiness and model load status  
- Swagger UI: [http://localhost:8088/docs](http://localhost:8088/docs)

## 🧪 Testing
Run all tests (unit + integration):
```bash
pytest -v --cov=src --cov-report=term-missing
```

## System Requirements
- Docker and Docker Compose
- MinIO instance with access credentials

## Notes
 • First startup may take ~30s to load the CNN14 model into memory.
 • Kafka alerts are optional; see `KAFKA_BROKERS` and `ALERTS_TOPIC`.
 • Database writes are handled through `classification.core.db_io_pg`.