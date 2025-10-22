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

1. Open the config file app/config.py.

2. Add the table name under the ALLOWED_TABLES list.

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
