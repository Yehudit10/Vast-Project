# DB API Service

This project provides a lightweight **FastAPI** service that exposes REST endpoints
for interacting with a PostgreSQL database table `files` (with PostGIS geometry and JSONB support).

## Features
- **Authentication**: Bearer token required (`API_TOKEN`).
- **CRUD** operations on `files` table:
  - `POST /api/files` → Insert or UPSERT a file record.
  - `PUT /api/files/{bucket}/{object_key}` → Update existing record fields.
  - `GET /api/files/{bucket}/{object_key}` → Retrieve single record.
  - `GET /api/files` → List recent records (with optional filters).
- **PostGIS**: `footprint` stored as geometry (SRID 4326).
- **JSONB**: `metadata` stored as JSONB.
- **Dry-run mode**: `DB_DRY_RUN=1` spools payloads to JSON files without touching the DB.

## Requirements
- Docker
- PostgreSQL with:
  ```sql
  CREATE EXTENSION IF NOT EXISTS postgis;


Environment Variables
API_TOKEN – Bearer token required in requests.

DB_DSN – SQLAlchemy DSN for PostgreSQL, e.g. postgresql+psycopg://user:pass@host:5432/db.

DB_DRY_RUN – if set to 1, all requests are spooled locally instead of writing to DB.

DRY_RUN_SPOOL – directory for spooled JSON (default: /tmp/api_spool).

## Build and Run
# Build Docker image:

bash
Copy code
docker build -t db-api:latest ./db_api



# Run container with PostgreSQL connection:

bash
Copy code
docker run -d --name db-api \
  -p 8080:8080 \
  -e API_TOKEN=dev-token \
  -e DB_DSN="postgresql+psycopg://postgres:postgres@postgres:5432/postgres" \
  db-api:latest
Quick Tests
bash
Copy code
# Health check
curl -fsS http://localhost:8080/healthz

# Readiness (always returns ready=true in current version)
curl -fsS http://localhost:8080/ready

# List files (requires Bearer token)
curl -s -H "Authorization: Bearer dev-token" \
  "http://localhost:8080/api/files?bucket=hot&limit=10"

# UPSERT a file
curl -s -X POST -H "Authorization: Bearer dev-token" -H "Content-Type: application/json" \
  -d '{"bucket":"hot","object_key":"imagery/a.jpg","size_bytes":1234,"metadata":{"a":1}}' \
  http://localhost:8080/api/files

# Update fields (PUT)
curl -s -X PUT -H "Authorization: Bearer dev-token" -H "Content-Type: application/json" \
  -d '{"content_type":"image/jpeg","footprint":"POLYGON((...))"}' \
  http://localhost:8080/api/files/hot/imagery/a.jpg
