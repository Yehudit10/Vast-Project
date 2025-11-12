# Soil Moisture DL Pipeline – Real-Time Irrigation Control (ONNX Inference)

This repository delivers an end-to-end **deep learning** pipeline to detect soil moisture state
(**wet / dry**) from ground-level RGB images and trigger **real-time irrigation** actions.

## Highlights
- **Training (PyTorch)**: MobileNetV3-small (transfer learning) + augmentations.
- **Export** to **ONNX** for light-weight **CPU/Jetson** inference.
- **Inference Service (FastAPI)**:
  - Tiling into patches
  - Per-patch ONNX inference
  - Zone policy with hysteresis (dry_ratio_high / dry_ratio_low / min_patches)
  - **Kafka** publish to `irrigation.control` (idempotent) + DLQ
  - **Postgres** persistence in `soil_moisture_events` (+ optional schedule UPSERT + audit)
  - **Prometheus** metrics + health/ready endpoints

---

## Run

```bash
docker compose up -d api
```

The API will be available at: [http://localhost:8000](http://localhost:8000)

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Basic health check |
| `GET` | `/ready` | Checks DB connectivity |
| `GET` | `/metrics` | Prometheus metrics |
| `POST` | `/infer` | Run inference on uploaded image |

### Example request

```bash
curl -X POST "http://localhost:8000/infer"      -F "zone_id=zone1"      -F "image=@sample.jpg"
```

Response:
```json
{
  "device_id": "zone1",
  "dry_ratio": 0.42,
  "decision": "stop",
  "confidence": 0.87,
  "patch_count": 48,
  "ts": "2025-10-29T09:41:00Z",
  "idempotency_key": "zone1:345621"
}
```

---

## Environment Variables

| Name | Description | Example |
|------|--------------|----------|
| `PG_DSN` | Postgres connection string | `postgresql://user:pass@host.docker.internal:5432/missions_db` |
| `KAFKA_BROKERS` | Kafka brokers | `kafka:9092` |
| `KAFKA_TOPIC` | Kafka topic for irrigation control | `irrigation.control` |
| `KAFKA_DLT` | Kafka DLQ topic | `irrigation.control.dlq` |
| `ZONES_FILE` | Path to zone configuration | `/app/configs/zones.yaml` |
| `SCHEDULE_UPDATE` | Enables schedule table update | `1` |
| `DECISION_WINDOW_SEC` | Time window for decision hysteresis | `3` |

---

## Notes
- The service depends on Postgres and Kafka within the `ag_cloud` Docker network.  
- If Kafka is unreachable, messages are logged but not published.  
- Duplicate inferences are prevented using an idempotency key per decision window.  
- Metrics exposed for Prometheus under `/metrics`.

---

## Example Compose Context

```yaml
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    environment:
      PG_DSN: postgresql://missions_user:pg123@host.docker.internal:5432/missions_db
      KAFKA_BROKERS: kafka:9092
      KAFKA_TOPIC: irrigation.control
      KAFKA_DLT: irrigation.control.dlq
      ZONES_FILE: /app/configs/zones.yaml
      DECISION_WINDOW_SEC: 3
      PATCH_SIZE: 256
      PATCH_STRIDE: 256
      SCHEDULE_UPDATE: 1
    volumes:
      - ./configs:/app/configs
      - ./artifacts:/app/artifacts
    ports:
      - "8000:8000"
    networks:
      - ag_cloud
```

---

## Testing

```bash
pytest -v
```

---

## License
Internal AgCloud component – for research and development use only.
