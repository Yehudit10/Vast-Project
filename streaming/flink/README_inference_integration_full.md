# README – Integrating a New Model Service into the Inference Flow (Kafka → Flink → HTTP)

This document explains how to integrate a new model inference service into the generic flow: **Kafka → Flink Dispatcher → HTTP Inference Service**, without creating any new Dockerfiles.

---

## Table of Contents
1. Overview
2. Existing Components
3. Recommended Directory Structure
4. Step-by-Step Integration Guide
5. Adapter Template
6. Updating the Model Registry
7. Adding Services to docker-compose
8. Kafka Input Message Schema
9. Health and Integration Testing
10. Common Troubleshooting
11. Quick Checklist for New Teams
12. FAQ

---

## 1) Overview
- The **generic HTTP inference service** under `services/inference_http` exposes the endpoint `/infer_json`, which accepts `{bucket, key}` and returns the model’s output.
- The **Flink Dispatcher** consumes from the topic `imagery.new.<team>`, performs HTTP requests, and routes results to success or DLQ topics.
- New teams **do not create new Dockerfiles**. Instead, they only:
  1) Add a new Adapter (Runner) for their model.
  2) Add a new case to `model_registry.py`.
  3) Add two compose services: `<team>-inference-http` and `flink-dispatcher-<team>`.
  4) Optionally update `requirements.txt` if extra dependencies are needed.

---

## 2) Existing Components
- `services/inference_http/app.py` – FastAPI app exposing `/infer_json`, which retrieves objects from MinIO and runs the correct runner based on `TEAM`.
- `services/inference_http/model_registry.py` – Function `get_model_runner(team)` returning the proper runner instance.
- `services/inference_http/adapters/fruit_defect_runner.py` – Example adapter for loading weights and running inference.
- `streaming/flink/jobs/http_dispatcher.py` – PyFlink job that consumes Kafka messages and performs HTTP inference calls.
- Example compose services: `fruit-inference-http` (HTTP) and `flink-dispatcher-fruit` (Dispatcher).

---

## 3) Recommended Directory Structure
```
services/
  inference_http/
    app.py
    model_registry.py
    requirements.txt
    adapters/
      fruit_defect_runner.py
      <team_name>_runner.py      # your new runner
    models/
      fruit_defect/...           # example
      <team_name>/...            # your model code (without weights)
    weights/
      fruit_cls_best.ts
      <team_name>_best.pt        # your model weights (mounted as volume)
```
> Model weights are loaded from `/app/weights` inside the container. Read their path from the `WEIGHTS_PATH` environment variable.

---

## 4) Step-by-Step Integration Guide
1. **Add model code** to `services/inference_http/models/<team_name>/...` (exclude weights).
2. **Create an Adapter (Runner)** at `services/inference_http/adapters/<team_name>_runner.py` (see template below).
3. **Update the Model Registry** by adding a case for `<team_name>`.
4. **Place your weights** in `services/inference_http/weights/` and set `WEIGHTS_PATH` if the filename differs.
5. **Dependencies** – if new Python packages are required, add them to `services/inference_http/requirements.txt`. Prefer wheels. If system (apt) packages are required, Dockerfile changes may be necessary (rare case).
6. **Add HTTP service** to compose as `<team>-inference-http` with `TEAM=<team>` and a volume for weights.
7. **Add Flink Dispatcher** as `flink-dispatcher-<team>` consuming from `imagery.new.<team>` and calling `http://<team>-inference-http:8000/infer_json`.
8. **Check health** using `/healthz`.
9. **Test inference manually** via `curl`.
10. **Send a Kafka test message** to verify full flow.

---

## 5) Adapter Template
`services/inference_http/adapters/<team_name>_runner.py`
```python
from typing import Any, Dict, Optional

class TeamXRunner:
    def __init__(self, weights_path: Optional[str] = None, model_tag: Optional[str] = None):
        import os
        self.weights_path = weights_path or os.getenv("WEIGHTS_PATH", "/app/weights/<team_name>_best.pt")
        self.model_tag = model_tag
        # TODO: Load model, e.g. torch.load(self.weights_path)
        # self.model = load_model(self.weights_path)

    def run(self, image_bytes_or_uri: Any, model_tag: Optional[str] = None, extra: Optional[Dict] = None) -> Dict:
        # image_bytes_or_uri may be raw image bytes or URI (e.g. s3://bucket/key)
        # TODO: Preprocess, infer, postprocess
        return {
            "label": "example_label",
            "score": 0.99,
            "confidence": 0.99,
            "latency_ms_model": 12
        }
```
> **Recommended output keys:** `label`, `score`, `confidence`, `latency_ms_model`.

---

## 6) Updating the Model Registry
`services/inference_http/model_registry.py`
```python
from adapters.fruit_defect_runner import FruitRunner
from adapters.<team_name>_runner import TeamXRunner  # new

def get_model_runner(team: str):
    t = (team or "").lower()
    if t == "fruit":
        return FruitRunner()
    if t == "<team_name>":
        return TeamXRunner()
    raise ValueError(f"unknown TEAM {t}")
```

---

## 7) Adding Services to docker-compose

### 7.1 HTTP Service
```yaml
  <team>-inference-http:
    build:
      context: ./services/inference_http
      dockerfile: Dockerfile
    environment:
      - TEAM=<team>
      - WEIGHTS_PATH=/app/weights/<team_name>_best.pt  # optional
      # - MINIO_ENDPOINT=minio-hot:9000
      # - MINIO_ACCESS_KEY=minioadmin
      # - MINIO_SECRET_KEY=minioadmin123
      # - MINIO_SECURE=0
    volumes:
      - ./services/inference_http/weights:/app/weights:ro
    depends_on:
      - minio-hot
    networks: [ag_cloud]
    restart: unless-stopped
    # ports:
    #   - "8001:8000"  # optional for local testing
```

### 7.2 Flink Dispatcher Service
```yaml
  flink-dispatcher-<team>:
    image: agcloud-flink-py:1.18
    container_name: flink-dispatcher-<team>
    depends_on:
      flink-jobmanager: { condition: service_started }
      flink-taskmanager: { condition: service_started }
      <team>-inference-http: { condition: service_started }
    networks: [ag_cloud]
    environment:
      - KAFKA_BOOTSTRAP=kafka:9092
      - INPUT_TOPIC=imagery.new.<team>
      - TEAM=<team>
      - HTTP_URL=http://<team>-inference-http:8000/infer_json
      - DLQ_TOPIC=dlq.inference.http
      - GROUP_ID=http-dispatcher-<team>
      - PARALLELISM=2
      - PYFLINK_CLIENT_EXECUTABLE=/usr/bin/python3
    volumes:
      - ./streaming/flink/jobs:/opt/flink/jobs:ro
      - ./streaming/flink/connectors:/opt/flink/lib:ro
    command: [
      "bash","-lc",
      "set -e;\n\n      echo 'Waiting for JobManager...';\n      until /opt/flink/bin/flink list --jobmanager flink-jobmanager:8081 >/dev/null 2>&1; do\n        echo 'still waiting...'; sleep 3;\n      done;\n      echo 'JobManager ready!';\n\n      /opt/flink/bin/flink run \
        -Dpython.client.executable=/usr/bin/python3 \
        -Dpython.executable=/usr/bin/python3 \
        --jobmanager flink-jobmanager:8081 \
        --detached \
        --python /opt/flink/jobs/http_dispatcher.py \
        -- \
          --bootstrap ${KAFKA_BOOTSTRAP} \
          --input-topic ${INPUT_TOPIC} \
          --team ${TEAM} \
          --http-url ${HTTP_URL} \
          --group-id ${GROUP_ID} \
          --dlq-topic ${DLQ_TOPIC};\n      tail -f /dev/null"
    ]
```

---

## 8) Kafka Input Message Schema
Input topic: `imagery.new.<team>`
```json
{
  "bucket": "imagery-hot",
  "key": "path/to/image.jpg",
  "camera": "<optional>",
  "publish_ts_ms": 1699999999999
}
```
**Required fields:** `bucket` and `key`.

---

## 9) Health and Integration Testing
1. **Check HTTP Health**:
   ```bash
   curl http://<team>-inference-http:8000/healthz
   ```
   Expected: `{ "ok": true, "team": "<team>" }`

2. **Manual Inference Test**:
   ```bash
   curl -X POST http://<team>-inference-http:8000/infer_json         -H 'Content-Type: application/json'         -d '{"bucket":"imagery-hot","key":"path/to/image.jpg"}'
   ```

3. **End-to-End Flow Test**:
   Send a Kafka message to `imagery.new.<team>` and confirm results or DLQ entries.

---

## 10) Common Troubleshooting
- **HTTP service fails to start** → check `TEAM` env and `model_registry.py` entry.
- **Weights not found** → verify `WEIGHTS_PATH` and volume mapping.
- **ImportError in Adapter** → add dependencies to `requirements.txt` and rebuild.
- **HTTP timeout** → verify network `ag_cloud`, correct `HTTP_URL`, and resource load.
- **Kafka serialization/auth** → ensure connector JAR versions match and are mounted correctly.

---

## 11) Quick Checklist for New Teams
- [ ] Add model under `models/<team>`
- [ ] Create adapter `adapters/<team>_runner.py`
- [ ] Add case to `model_registry.py`
- [ ] Place weights in `weights/`
- [ ] Update `requirements.txt` if needed
- [ ] Add `<team>-inference-http` to compose
- [ ] Add `flink-dispatcher-<team>` to compose
- [ ] Verify `/healthz` and `/infer_json`
- [ ] Send Kafka test message

---

## 12) FAQ
**Q: Do we need a new Dockerfile?**  
A: No, unless you require non-Python system dependencies.

**Q: Where do weights go?**  
A: In `services/inference_http/weights`, mounted to `/app/weights`. Define `WEIGHTS_PATH` if the filename differs.

**Q: Which fields are required in Kafka messages?**  
A: `bucket` and `key`.

**Q: How can I test quickly?**  
A: Use `/healthz`, send a test `/infer_json`, then a Kafka message to `imagery.new.<team>`.
