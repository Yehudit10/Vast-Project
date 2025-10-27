# Storage DB API

A FastAPI microservice for managing image/file metadata in the **AgCloud** platform.

## Quickstart (Docker Compose)

Build:
```bash
docker compose up -d --build
```

Check health:
```bash
curl http://localhost:8080/healthz
curl http://localhost:8080/ready
```

Stop and clean up:
```bash
docker compose down
```

## Generic API Support
The service now includes a Generic API layer that automatically exposes CRUD endpoints for allowed database tables.

To enable a table:

Add the table name under the ALLOWED_TABLES list in the ENV file

## Authentication

### Dev bootstrap
For local development only – creates default user (`admin`) and service account (`db-api`):

```bash
curl -X POST http://localhost:8080/auth/_dev_bootstrap
```

Response includes:
- User and Service Account (created if missing).
- JWT access & refresh tokens.
- Raw service token (only shown once if newly created).

---

### Human users (username/password)

Login:
```bash
curl -s -X POST http://localhost:8080/auth/login   -H "Content-Type: application/x-www-form-urlencoded"   -d "username=admin&password=admin123"
```

Use the returned `access_token` in the `Authorization` header:

```http
Authorization: Bearer <access_token>
```

Refresh:
```bash
curl -s -X POST http://localhost:8080/auth/refresh   -H "Content-Type: application/json"   -d '{"refresh_token":"<refresh_token>"}'
```

---

### Service-to-service

Use the `X-Service-Token` header with the raw token received during bootstrap (or after manual rotation):

```http
X-Service-Token: <raw-service-token>
```

---

## Example API call

With JWT (user):
```powershell
$boot = Invoke-WebRequest -Method POST "http://localhost:8080/auth/_dev_bootstrap"
$j = $boot.Content | ConvertFrom-Json
$access = $j.tokens.access_token

Invoke-WebRequest "http://localhost:8080/api/files?limit=2" `
  -Headers @{ Authorization = ("Bearer {0}" -f $access) }
```

With Service Token (service account):
```powershell
Invoke-WebRequest "http://localhost:8080/api/files?limit=2" `
  -Headers @{ "X-Service-Token" = "<raw-service-token>" }
```

---

---

## Example: Generic API Usage

The Generic API provides unified CRUD endpoints for any allowed table.

### Available endpoints
| Method | Endpoint | Description |
|--------|-----------|-------------|
| GET | `/api/tables/{resource}/schema` | Get table schema |
| GET | `/api/tables/{resource}` | List rows |
| POST | `/api/tables/{resource}` | Create a single row |
| POST | `/api/tables/{resource}/rows:batch` | Create multiple rows in one request |

### Example 1 — List rows
```bash
curl -X GET "http://localhost:8080/api/tables/event_logs_sensors?limit=5" \
  -H "Authorization: Bearer <access_token>"
```

## Networking & Access

When running via Docker Compose, all services share the same internal network automatically.  
You can access the API at:

http://localhost:8080

If other services need to reach it internally, use the service name defined in `docker-compose.yml`
(for example `db-api`).

### Example 2 — Create a single row
```bash
curl -X POST "http://localhost:8080/api/tables/event_logs_sensors" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
        "device_id": "dev-a",
        "issue_type": "temperature_out_of_range",
        "severity": "warn",
        "start_ts": "2025-10-15T20:09:02.065445+03:00",
        "details": {"measured": 52.4, "expected_range": [0, 50], "unit": "°C"}
      }'
```


---

## Testing readme in /test


---

## Notes
- Changing `JWT_SECRET` invalidates all existing JWTs.
- Service tokens are **write-once**: only the raw token (from bootstrap or rotation) can be used; the DB only stores its SHA-256 hash.
- `/auth/_dev_bootstrap` is intended for development only – do not enable in production.

## API Examples (CRUD)

Base URL: http://localhost:8080 (adjust if different)
Prefix used below: /api/tables/{resource}

Replace `{resource}` with the table name (e.g. `event_logs_sensors`). Ensure `Content-Type: application/json` header.

Create — single row (POST /api/tables/{resource})
```bash
curl -X POST "http://localhost:8080/api/tables/event_logs_sensors" \
  -H "Content-Type: application/json" \
  -d '{
    "log_id": 4,
    "device_id": "dev-c",
    "status": "ok",
    "value": 12.3
  }'
# Response: {"affected_rows":1,"returning":{...}}
```

Create — batch (POST /api/tables/{resource}/rows:batch)
```bash
curl -X POST "http://localhost:8080/api/tables/event_logs_sensors/rows:batch" \
  -H "Content-Type: application/json" \
  -d '[
    {"log_id": 5, "device_id":"dev-a", "status":"ok"},
    {"log_id": 6, "device_id":"dev-b", "status":"error"}
  ]'
# Response: {"affected_rows":2}
```

Read — list rows (GET /api/tables/{resource})
```bash
curl "http://localhost:8080/api/tables/event_logs_sensors?limit=20&offset=0&order_by=log_id&order_dir=asc"
# Response: {"rows":[...],"count":N}
```

Read — describe table / schema (GET /api/tables/{resource}/schema)
```bash
curl "http://localhost:8080/api/tables/event_logs_sensors/schema"
# Response: {"table":"event_logs_sensors","contract":{...},"columns":[...]}
```

Update — partial (PATCH /api/tables/{resource}/rows)
- body must include `keys` (identifying fields) and `data` (fields to update)
```bash
curl -X PATCH "http://localhost:8080/api/tables/event_logs_sensors/rows" \
  -H "Content-Type: application/json" \
  -d '{
    "keys": {"log_id": 4, "device_id": "dev-c"},
    "data": {"status": "resolved", "value": 15.0}
  }'
# Response: {"affected_rows":1,"returning":{...}}
```

Replace / full update (PUT /api/tables/{resource}/rows)
- body includes `keys` and a full `data` payload validated against the contract
```bash
curl -X PUT "http://localhost:8080/api/tables/event_logs_sensors/rows" \
  -H "Content-Type: application/json" \
  -d '{
    "keys": {"log_id": 4, "device_id": "dev-c"},
    "data": {
      "log_id": 4,
      "device_id": "dev-c",
      "status": "resolved",
      "value": 15.0,
      "ts": "2025-10-22T10:00:00Z"
    }
  }'
# Response: {"affected_rows":1,"returning":{...}}
```

Delete (DELETE /api/tables/{resource}/rows)
- body must include `keys` object
```bash
curl -X DELETE "http://localhost:8080/api/tables/event_logs_sensors/rows" \
  -H "Content-Type: application/json" \
  -d '{"keys": {"log_id": 4, "device_id": "dev-c"}}'
# Response: {"affected_rows":1}
```

Notes
- `keys` fields are determined by the contract's `x-keyFields` (fallback to `id` if not present). Use the schema endpoint to confirm.
- All validation is performed against the JSON contract; unknown fields are rejected.
- Adjust base URL, auth headers and query params as needed for your deployment.
