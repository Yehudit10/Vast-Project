# 🚨 AgGuard AlertManager Service

The **AgGuard AlertManager Service** acts as a bridge between AgCloud’s detection pipelines and **Prometheus Alertmanager**.  
It receives structured alert JSON payloads, renders descriptive messages using YAML templates, and forwards the alerts to Alertmanager’s `/api/v2/alerts` endpoint.

---

## 🧩 Overview

- **Framework:** FastAPI  
- **Purpose:** Converts raw alerts from detection systems into human-readable, templated messages and sends them to Alertmanager  
- **Output:** Properly structured Alertmanager v2 JSON alerts  
- **Version:** `1.3`

---

## ⚙️ Environment Variables

| Variable | Description | Default |
|-----------|--------------|----------|
| `CFG_PATH` | Path to the YAML file containing alert templates | `/app/templates/templates/templates.yml` |
| `ALERTMANAGER_URL` | Base URL of the Alertmanager API | `http://alertmanager:9093` |
| `LOG_LEVEL` | Optional logging verbosity (e.g., `INFO`, `DEBUG`) | `INFO` |

---

## 🚀 Endpoints

### `POST /alerts`

Accepts an alert JSON payload and forwards it to Alertmanager after rendering its template.

**Example request:**

```bash
curl -X POST http://localhost:8000/alerts \
  -H "Content-Type: application/json" \
  -d '{
    "alert_id": "alert-67",
    "alert_type": "smoke_detected",
    "device_id": "camera-12",
    "started_at": "2025-10-30T14:45:00Z",
    "ended_at": "2025-10-30T15:10:00Z",
    "confidence": 0.91,
    "severity": 2,
    "area": "south_field",
    "lat": 31.900215,
    "lon": 34.850921,
    "image_url": "https://s3.farm/agguard/smoke_20251030_1445.jpg",
    "vod": "https://s3.farm/agguard/smoke_clip_1445.mp4"
  }'
```

**Example response:**

```json
{
  "status": "sent",
  "alert": {
    "labels": {
      "alertname": "smoke_detected",
      "alert_id": "alert-67",
      "device": "camera-12",
      "source": "agcloud-alerts"
    },
    "annotations": {
      "summary": "🚨 Smoke detected by camera-12 near south_field (confidence 0.91)",
      "recommendation": "Inspect the south_field immediately. If fire is confirmed, contact emergency services.",
      "category": "environmental",
      "severity": "2",
      "lat": "31.900215",
      "lon": "34.850921",
      "image_url": "https://s3.farm/agguard/smoke_20251030_1445.jpg",
      "vod": "https://s3.farm/agguard/smoke_clip_1445.mp4"
    },
    "startsAt": "2025-10-30T14:45:00Z",
    "endsAt": "2025-10-30T15:10:00Z"
  }
}
```

---

### `GET /health`

Simple health check endpoint.

**Response:**

```json
{ "status": "ok" }
```

---

## 📄 Template Configuration

Templates are defined in a YAML file (default: `/app/templates/templates/templates.yml`).  
Each key corresponds to an `alert_type` and defines the message text and metadata.

**Example:**

```yaml
templates:
  smoke_detected:
    category: environmental
    summary: "🚨 Smoke detected by ${device_id} near ${area} (confidence ${confidence})"
    recommendation: "Inspect the ${area} immediately. If fire is confirmed, contact emergency services."

  masked_person:
    category: security
    summary: "Person wearing a mask detected by ${device_id} at ${timestamp}"
    recommendation: "Verify the person’s authorization using the live feed."
```

### 🧠 Template Variables

Template values use Python’s `string.Template` syntax (`${variable}`).  
Any key present in the incoming alert JSON can be substituted dynamically.

| Common variable | Description |
|------------------|-------------|
| `${device_id}` | Unique device identifier |
| `${area}` | Detected area/zone |
| `${confidence}` | Detection confidence |
| `${timestamp}` | ISO time string (optional) |
| `${alert_type}` | Type of alert |
| `${severity}` | Numeric severity or category |

If a template variable is missing in the payload, it is safely ignored (not replaced).

---

## 💬 How Templates Are Used in UI and Slack

- The `summary` field defined in the template is **displayed directly in the AgGuard UI alert panels**, providing human-readable context (e.g., _“🚨 Smoke detected by camera-12 near south_field”_).  
- The same `summary` text is also included in **Slack notifications** sent by Alertmanager, ensuring consistent and recognizable messages across interfaces.  
- `recommendation` text is used as an actionable suggestion in both the UI and Slack alerts (e.g., _“Inspect the south_field immediately.”_)

---

## 🧱 Expected JSON Fields

| Field | Required | Description |
|--------|-----------|-------------|
| `alert_id` | ✅ | Unique alert identifier |
| `alert_type` | ✅ | Type of alert (matches template name) |
| `device_id` | ✅ | Source device ID |
| `started_at` | ✅ | ISO timestamp (`Z` or timezone-aware) |
| `ended_at` | ❌ | ISO timestamp for resolution (optional) |
| `severity` | ❌ | Numeric or string-based severity |
| `confidence`, `area`, `lat`, `lon`, `image_url`, `vod`, `hls`, `meta` | ❌ | Optional metadata |

---

## 🧾 Example Alert Flow

1. **AgCloud Detector** sends a JSON alert to `/alerts`.  
2. The service loads the corresponding YAML template (based on `alert_type`).  
3. It renders the `summary`, `recommendation`, and `category` using `${variables}`.  
4. A properly formatted payload is sent to **Alertmanager v2 API**.  
5. Alertmanager handles grouping, silencing, and routing to receivers (e.g., Slack, email).  
6. The same summary is displayed in both **Slack messages** and the **AgGuard UI alerts**.

---

## 🧰 Local Run

```bash
# Install dependencies
pip install fastapi uvicorn pyyaml

# Run the service
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Environment variables can be provided via `.env` or Docker Compose:

```yaml
environment:
  - CFG_PATH=/app/templates/templates/templates.yml
  - ALERTMANAGER_URL=http://alertmanager:9093
```

---

## 🪶 Logging

Logs include alert processing details and delivery status:

```
2025-11-02 15:34:12 | INFO | [ALERT PAYLOAD] {
  "labels": { "alertname": "smoke_detected", ... },
  "annotations": { "summary": "...", ... },
  "startsAt": "..."
}
2025-11-02 15:34:12 | INFO | [Alertmanager] Sent alerts (HTTP 200)
```

---

