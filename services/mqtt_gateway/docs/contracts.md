# MQTT → MinIO → Kafka Data Contract

> Purpose: a stable, versioned contract for image ingestion events.
> Scope: mapping from publisher topic to MinIO object key and Kafka event.

## Example publisher file name
`garage_cam_01_20251027_121530.jpg`

## Kafka topic (value JSON published to this topic)
`rover.images.meta.v1`

## Kafka message (value)
```json
{
  "version": 1,
  "event_id": "8b0a6f2b-1f95-4b28-9870-5f7f1d4a6a11",
  "sensor_id": "camera-01",
  "captured_ts": 1761548130123,
  "image": {
    "bucket": "rover-images",
    "key": "images/camera-01/2025/10/27/camera-01_1761548130123.jpg",
    "size_bytes": 531245,
    "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "content_type": "image/jpeg"
  },
  "telemetry": {
    "lat": 32.061,
    "lon": 34.772,
    "heading": 182.4,
    "speed_mps": 2.1
  },
  "producer": "mqtt-gateway"
}
