# Storage DB API

A FastAPI microservice for managing image/file metadata in the **AgCloud** platform.

## Quickstart (Dockerfile)

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

## Networking & Access

**Host access (publish port, for development only):**
```bash
docker run --rm -d --name db-api-service-run   -p 127.0.0.1:8080:8080   --env-file .env   db-api-service:latest
```
Use `http://localhost:8080`. Bind to `127.0.0.1` for local-only, or change the host port (e.g. `8081`) to avoid conflicts.

**Inter-container access (same network, no published port required):**
```bash
docker network create api_net || true

docker run -d --name db-api --network api_net --env-file .env db-api-service:latest
docker run --rm --network api_net curlimages/curl:8.9.1 curl -s http://db-api:8080/healthz
```
Both containers must be on the same Docker network to resolve `db-api` by name.

---

## Testing readme in /test


---

## Notes
- Changing `JWT_SECRET` invalidates all existing JWTs.
- Service tokens are **write-once**: only the raw token (from bootstrap or rotation) can be used; the DB only stores its SHA-256 hash.
- `/auth/_dev_bootstrap` is intended for development only – do not enable in production.
