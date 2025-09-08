# 🚀 Quick Start – PostgreSQL + Monitoring Stack

This project sets up PostgreSQL (via Bitnami Helm on Minikube-in-Docker) together with Prometheus, Grafana, Alertmanager, and postgres_exporter.

## 1. Run Everything

```bash
docker compose up -d --build
```




## 2. Open the UIs

- Prometheus → [http://localhost:9090](http://localhost:9090)
- Grafana → [http://localhost:3000](http://localhost:3000) (login: `admin` / `admin`)

-- In Grafana you have to enter into dashboard and press new, and then import and choose the json file in this folder.(there is simple and multi you can choos)

That’s it — dashboards will already be provisioned and connected.

---

##  Verify in Prometheus / Grafana

In Prometheus UI run:
```
rate(pg_wal_stats_wal_bytes[5m])
```

In Grafana dashboard, check WAL throughput / BRIN / replication lag panels.

---

## 🔎 PostgreSQL with pgvector

The PostgreSQL image used in this project is extended from `bitnami/postgresql:16` and includes the [`pgvector`](https://github.com/pgvector/pgvector) extension.

### Build the image
From inside the `RelDB` directory:
```bash
docker build -t agcloud/postgresql-pgvector:16 -f pgvector.Dockerfile .
```

### Run the container
```bash
docker run --name agcloud-db \
  -e POSTGRESQL_POSTGRES_PASSWORD=SuperSecret123 \
  -e POSTGRESQL_USERNAME=agcloud \
  -e POSTGRESQL_PASSWORD=agcloud \
  -e POSTGRESQL_DATABASE=agcloud \
  -p 5432:5432 \
  -v pgdata:/bitnami/postgresql \
  -d agcloud/postgresql-pgvector:16
```

### Default credentials
- Superuser: `postgres` / `SuperSecret123`
- User: `agcloud` / `agcloud`

### Verify pgvector
Check installed extensions:
```bash
docker exec -it agcloud-db psql -U postgres -d agcloud -c "\dx"
```

If `vector` is not listed (e.g., on an existing volume), enable it manually:
```bash
docker exec -it agcloud-db psql -U postgres -d agcloud -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Example usage
```sql
CREATE TABLE items (id serial PRIMARY KEY, embedding vector(3));
INSERT INTO items (embedding) VALUES ('[1,2,3]'), ('[2,0,0]');
SELECT id, embedding
FROM items
ORDER BY embedding <=> '[1,2,3]'
LIMIT 1;
```


## Notes

- Default credentials:
  - postgres / `PgAdmin!ChangeMe123`
  - missions_user / `Missions!ChangeMe123`
- Configuration files:
  - `prometheus.yml`, `prometheus-recording.rules.yml`, `postgres-alerts.yml`
  - `grafana-datasource.yml`, `grafana-dashboards.yml`, `grafana-dashboard.json`
- All SQL init scripts under `/work/initdb` are automatically applied in order.

Enjoy your graphs! 🎉


# pitr
1. option to run munual bakcup:
```
docker exec -u postgres -it db python3 /usr/local/bin/backup.py
```

2. check database:
```
docker exec db psql -U missions_user -d missions_db -c "SELECT COUNT(*) AS row_count FROM anomalies;"

docker exec db psql -U missions_user -d missions_db -c "DELETE FROM anomalies WHERE anomaly_id = 123;"
```

## 🔄 Recovery (PITR – Point in Time Recovery)

We use the `recover.py` helper script to restore the database from base backups and WAL archives.

### 3. Recovery modes

- **Latest** → restore up to the latest available WAL:
```bash
  docker exec -u postgres -it db python3 /usr/local/bin/recover.py latest
```

- **Minutes ago** → restore to a point N minutes in the past:
```bash
  docker exec -u postgres -it db python3 /usr/local/bin/recover.py minutes 2
```

- **Exact time** → restore to a specific timestamp:
```bash
  docker exec -u postgres -it db python3 /usr/local/bin/recover.py time "2025-09-07T11:15:00+03:00"
```

# Restart the container

- After preparing the recovery files, the script will print:

[RECOVERY] Recovery setup complete ✅
[RECOVERY] Please restart the container to apply recovery:
           docker restart db

Run:
```bash
docker restart db
```

check not in recovery:
```bash
docker exec -it db psql -U missions_user -d missions_db -c "SELECT pg_is_in_recovery();"
```

wait for f, and run:
```bash
docker exec -u postgres -it db python3 /usr/local/bin/backup.py

```
