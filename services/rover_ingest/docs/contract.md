# Rover Image Metadata Contract

This contract defines the JSON payload for **still-image** ingestion events produced by a rover.
The image file itself is stored in **MinIO/S3** (not sent in the message). The message carries
the metadata required to **validate** and **index** the image in RelDB (Postgres).

## Required fields
```json
{
  "schema_ver": 1,
  "device_id": "rover-07",
  "image_id": "20250910T101500Z-abc123",
  "captured_at": "2025-09-10T10:15:00Z",
  "gps": { "lat": 31.7767, "lon": 35.2345, "gps_accuracy_m": 2.4 },
  "heading_deg": 247.3,
  "alt_m": 1.6,
  "s3_key": "rover-images/rover-07/2025/09/10/20250910T101500Z-abc123.jpg",
  "meta_src": "manifest"
}
```

Notes:
- `captured_at` is UTC ISO-8601.
- `heading_deg` is camera yaw relative to North in **[0,360)**.
- `alt_m` is camera height above ground in meters (if unknown set `null`).

---

## Recommended fields
```json
{
  "pitch_deg": 0.0,
  "roll_deg": 0.0,
  "fov_deg": 78.0,
  "temp_c": 27.5,
  "mime_type": "image/jpeg",
  "size_bytes": 532112,
  "sha256": "0123abcd...",
  "exif_present": false,
  "firmware": "cam-fw-1.8.2",
  "capture_seq": 418,
  "signature": "base64(hmac-or-jws)",
  "trace_id": "b4932a9f-...-6132",
  "source_ts": "2025-09-10T10:15:00.050Z"
}
```

---
## 3. Validation rules (summary)

- **Time**: `captured_at` must not be in the future. If `source_ts` exists, the absolute
  delta `|captured_at - source_ts|` should be ≤ 5 minutes.
- **GPS**: `-90 ≤ lat ≤ 90`, `-180 ≤ lon ≤ 180`.
- **Heading**: normalized to `[0,360)`.
- **Storage**: `s3_key` **must** exist in MinIO/S3 bucket (`HEAD`/`stat` check).
- **Idempotency**: `image_id` is the primary key. If the same image is re-sent,
  fields are **upserted** (see DB mapping). If `sha256` is present, it must be unique.

---

## 4. Mapping to DB (Postgres schema `rover`)

| JSON field                                      | DB column                      |
|------------------------------------------------|--------------------------------|
| `image_id`                                     | `rover.images.image_id`        |
| `device_id`                                    | `rover.images.device_id`       |
| `captured_at`                                  | `rover.images.captured_at`     |
| `gps.lat`, `gps.lon`                           | `rover.images.lat`, `lon`      |
| `gps.gps_accuracy_m`                           | `rover.images.gps_accuracy_m`  |
| `heading_deg`, `pitch_deg`, `roll_deg`         | same-named columns             |
| `alt_m`, `fov_deg`, `temp_c`                   | same-named columns             |
| `s3_key`, `mime_type`, `size_bytes`, `sha256`  | same-named columns             |
| `exif_present`, `firmware`, `capture_seq`      | same-named columns             |
| `meta_src`, `schema_ver`, `source_ts`, `trace_id` | same-named columns          |

---

## 5. NDJSON examples (one object per line)

```ndjson
{"schema_ver":1,"device_id":"rover-07","image_id":"20250910T101500Z-abc123","captured_at":"2025-09-10T10:15:00Z","gps":{"lat":31.7767,"lon":35.2345,"gps_accuracy_m":2.4},"heading_deg":247.3,"alt_m":1.6,"s3_key":"rover-images/rover-07/2025/09/10/20250910T101500Z-abc123.jpg","meta_src":"manifest","mime_type":"image/jpeg","size_bytes":532112}
{"schema_ver":1,"device_id":"rover-07","image_id":"20250910T101800Z-def456","captured_at":"2025-09-10T10:18:00Z","gps":{"lat":31.7772,"lon":35.2351},"heading_deg":5.0,"alt_m":1.6,"s3_key":"rover-images/rover-07/2025/09/10/20250910T101800Z-def456.jpg","meta_src":"manifest","temp_c":27.9,"sha256":"4b1f...aa"}
```

---

## 6. Security notes
- Prefer **no EXIF** in image files; keep sensitive metadata in this JSON + DB.
- Sign messages (HMAC/JWS) if applicable. Validate bucket/key with least-privilege IAM.
