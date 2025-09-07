<<<<<<< HEAD
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

bash# DB API Service

This project provides a lightweight **FastAPI** service that exposes REST endpoints  
for interacting with a PostgreSQL `files` table (with PostGIS geometry and JSONB support).

---

## ✨ Features
- **Authentication**: All requests require a Bearer token (`API_TOKEN`).
- **CRUD operations** on the `files` table:
  - `POST /api/files` → Insert or **upsert** a file record.
  - `PUT /api/files/{bucket}/{object_key}` → Update fields of an existing record.
  - `GET /api/files/{bucket}/{object_key}` → Retrieve a single record.
  - `GET /api/files` → List recent records (with optional filters).
  - `DELETE /api/files/{bucket}/{object_key}` → Delete a record.
- **PostGIS**: `footprint` stored as geometry (SRID 4326).
- **JSONB**: `metadata` stored as JSONB.
- **Dry-run mode**: `DB_DRY_RUN=1` → spool payloads to JSON files without touching the DB.

---

## 📦 Requirements
- Docker
- PostgreSQL with PostGIS:
  ```sql
  CREATE EXTENSION IF NOT EXISTS postgis;
  ```

---

## ⚙️ Environment Variables
| Name           | Description                                                        | Default              |
|----------------|--------------------------------------------------------------------|----------------------|
| `API_TOKEN`    | Bearer token required in requests                                  | –                    |
| `DB_DSN`       | SQLAlchemy DSN, e.g. `postgresql+psycopg://user:pass@host:5432/db` | –                    |
| `DB_DRY_RUN`   | If set to `1`, requests are spooled locally (no DB writes)         | `0`                  |
| `DRY_RUN_SPOOL`| Directory for spooled JSON files                                   | `/tmp/api_spool`     |

---

## 🚀 Build & Run

### Build Docker image
```bash
docker build -t db-api:latest ./db_api
```

### Run container with PostgreSQL connection

#### WSL / Linux
```bash
docker run -d --name db-api   -p 8080:8080   -e API_TOKEN=dev-token   -e DB_DSN="postgresql+psycopg://missions_user:pg123@localhost:5432/missions_db"   db-api:latest
```

#### Windows (Docker Desktop)
```bash
docker run -d --name db-api   -p 8080:8080   --add-host=host.docker.internal:host-gateway   -e API_TOKEN=dev-token   -e DB_DSN="postgresql+psycopg://missions_user:pg123@host.docker.internal:5432/missions_db"   db-api:latest
```

---

## ✅ Quick Tests

### Health checks
```bash
curl -fsS http://localhost:8080/healthz
# {"status":"ok"}

curl -fsS http://localhost:8080/ready
# {"ready":true}
```

### List files
```bash
curl -s -H "Authorization: Bearer dev-token"   "http://localhost:8080/api/files?bucket=hot&limit=10"
```

### Insert / Upsert a file
```bash
ts=$(date +%s)

curl -s -X POST -H "Authorization: Bearer dev-token" -H "Content-Type: application/json"   --data-binary '{
    "bucket":"hot",
    "object_key":"imagery/new-file-'"$ts"'.jpg",
    "content_type":"image/jpeg",
    "size_bytes":1234,
    "etag":"etag-new-file-'"$ts"'",
    "mission_id":1,
    "device_id":"dev-a",
    "metadata":{"source":"via-api","note":"insert test"}
  }'   http://localhost:8080/api/files
```

### Update fields
```bash
curl -s -X PUT -H "Authorization: Bearer dev-token" -H "Content-Type: application/json"   --data-binary '{
    "size_bytes": 9999,
    "metadata": {"source":"via-api","note":"updated via PUT"}
  }'   http://localhost:8080/api/files/hot/imagery/new-file-$ts.jpg
```

### Get single file
```bash
curl -s -H "Authorization: Bearer dev-token"   http://localhost:8080/api/files/hot/imagery/new-file-$ts.jpg
```

### Delete file
```bash
curl -s -X DELETE -H "Authorization: Bearer dev-token"   http://localhost:8080/api/files/hot/imagery/new-file-$ts.jpg
```

---

## 🛠️ Troubleshooting
- **Not Found on PUT/DELETE/GET** → make sure `router.py` uses:
  ```python
  @router.put("/{bucket}/{object_key:path}")
  @router.get("/{bucket}/{object_key:path}")
  @router.delete("/{bucket}/{object_key:path}")
  ```
- **Connection refused** → check PostgreSQL is running and accessible from the container.
- **Check row count**:
  ```bash
  docker exec -it postgres psql -U missions_user -d missions_db -c "SELECT COUNT(*) FROM files;"
  ```

Copy code
# WSL
docker run -d --name db-api \
  -p 8080:8080 \
  -e API_TOKEN=dev-token \
  -e DB_DSN="postgresql+psycopg://missions_user:pg123@localhost:5432/missions_db" \
  db-api:latest

# windows
docker run -d --name db-api \
  -p 8080:8080 \
  --add-host=host.docker.internal:host-gateway \
  -e API_TOKEN=dev-token \
  -e DB_DSN="postgresql+psycopg://missions_user:pg123@host.docker.internal:5432/missions_db" \
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
=======
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

bash# DB API Service

This project provides a lightweight **FastAPI** service that exposes REST endpoints  
for interacting with a PostgreSQL `files` table (with PostGIS geometry and JSONB support).

---

## ✨ Features
- **Authentication**: All requests require a Bearer token (`API_TOKEN`).
- **CRUD operations** on the `files` table:
  - `POST /api/files` → Insert or **upsert** a file record.
  - `PUT /api/files/{bucket}/{object_key}` → Update fields of an existing record.
  - `GET /api/files/{bucket}/{object_key}` → Retrieve a single record.
  - `GET /api/files` → List recent records (with optional filters).
  - `DELETE /api/files/{bucket}/{object_key}` → Delete a record.
- **PostGIS**: `footprint` stored as geometry (SRID 4326).
- **JSONB**: `metadata` stored as JSONB.
- **Dry-run mode**: `DB_DRY_RUN=1` → spool payloads to JSON files without touching the DB.

---

## 📦 Requirements
- Docker
- PostgreSQL with PostGIS:
  ```sql
  CREATE EXTENSION IF NOT EXISTS postgis;
  ```

---

## ⚙️ Environment Variables
| Name           | Description                                                        | Default              |
|----------------|--------------------------------------------------------------------|----------------------|
| `API_TOKEN`    | Bearer token required in requests                                  | –                    |
| `DB_DSN`       | SQLAlchemy DSN, e.g. `postgresql+psycopg://user:pass@host:5432/db` | –                    |
| `DB_DRY_RUN`   | If set to `1`, requests are spooled locally (no DB writes)         | `0`                  |
| `DRY_RUN_SPOOL`| Directory for spooled JSON files                                   | `/tmp/api_spool`     |

---

## 🚀 Build & Run

### Build Docker image
```bash
docker build -t db-api:latest ./db_api
```

### Run container with PostgreSQL connection

#### WSL / Linux
```bash
docker run -d --name db-api   -p 8080:8080   -e API_TOKEN=dev-token   -e DB_DSN="postgresql+psycopg://missions_user:pg123@localhost:5432/missions_db"   db-api:latest
```

#### Windows (Docker Desktop)
```bash
docker run -d --name db-api   -p 8080:8080   --add-host=host.docker.internal:host-gateway   -e API_TOKEN=dev-token   -e DB_DSN="postgresql+psycopg://missions_user:pg123@host.docker.internal:5432/missions_db"   db-api:latest
```

---

## ✅ Quick Tests

### Health checks
```bash
curl -fsS http://localhost:8080/healthz
# {"status":"ok"}

curl -fsS http://localhost:8080/ready
# {"ready":true}
```

### List files
```bash
curl -s -H "Authorization: Bearer dev-token"   "http://localhost:8080/api/files?bucket=hot&limit=10"
```

### Insert / Upsert a file
```bash
ts=$(date +%s)

curl -s -X POST -H "Authorization: Bearer dev-token" -H "Content-Type: application/json"   --data-binary '{
    "bucket":"hot",
    "object_key":"imagery/new-file-'"$ts"'.jpg",
    "content_type":"image/jpeg",
    "size_bytes":1234,
    "etag":"etag-new-file-'"$ts"'",
    "mission_id":1,
    "device_id":"dev-a",
    "metadata":{"source":"via-api","note":"insert test"}
  }'   http://localhost:8080/api/files
```

### Update fields
```bash
curl -s -X PUT -H "Authorization: Bearer dev-token" -H "Content-Type: application/json"   --data-binary '{
    "size_bytes": 9999,
    "metadata": {"source":"via-api","note":"updated via PUT"}
  }'   http://localhost:8080/api/files/hot/imagery/new-file-$ts.jpg
```

### Get single file
```bash
curl -s -H "Authorization: Bearer dev-token"   http://localhost:8080/api/files/hot/imagery/new-file-$ts.jpg
```

### Delete file
```bash
curl -s -X DELETE -H "Authorization: Bearer dev-token"   http://localhost:8080/api/files/hot/imagery/new-file-$ts.jpg
```

---

## 🛠️ Troubleshooting
- **Not Found on PUT/DELETE/GET** → make sure `router.py` uses:
  ```python
  @router.put("/{bucket}/{object_key:path}")
  @router.get("/{bucket}/{object_key:path}")
  @router.delete("/{bucket}/{object_key:path}")
  ```
- **Connection refused** → check PostgreSQL is running and accessible from the container.
- **Check row count**:
  ```bash
  docker exec -it postgres psql -U missions_user -d missions_db -c "SELECT COUNT(*) FROM files;"
  ```

Copy code
# WSL
docker run -d --name db-api \
  -p 8080:8080 \
  -e API_TOKEN=dev-token \
  -e DB_DSN="postgresql+psycopg://missions_user:pg123@localhost:5432/missions_db" \
  db-api:latest

# windows
docker run -d --name db-api \
  -p 8080:8080 \
  --add-host=host.docker.internal:host-gateway \
  -e API_TOKEN=dev-token \
  -e DB_DSN="postgresql+psycopg://missions_user:pg123@host.docker.internal:5432/missions_db" \
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
>>>>>>> 2ab8ea6 (Add tests)
