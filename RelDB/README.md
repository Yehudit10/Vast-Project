# PostgreSQL + PostGIS – Quick Start

## Build and Run
```powershell
# From the project folder
docker compose up -d --build
```

This will start a container named **postgres** on port `5432`.

---

## Check if it is running
```powershell
# See if the container is healthy
docker ps

# Connect and verify the database
docker exec -it postgres psql -U missions_user -d missions_db -c "SELECT current_database();"
```

Expected output:
```
 current_database
------------------
 missions_db
```

---

## How to Connect

You can connect from **outside the container** (your host or another machine) using the host `localhost`, port `5432`, database `missions_db`, user `missions_user`, and the password defined in your `docker-compose.yml` (for example `pg123`).

Below are examples using psql and Python.

### Example: psql from host
```powershell
psql "host=localhost port=5432 dbname=missions_db user=missions_user password=pg123"
```

### Example: Python (SQLAlchemy + psycopg)
```python
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql+psycopg://missions_user:pg123@localhost:5432/missions_db"
)

with engine.connect() as conn:
    rows = conn.execute("SELECT current_database();")
    for r in rows:
        print(r)
```
