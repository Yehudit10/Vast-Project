# PostgreSQL Monitoring Stack

This project sets up a full observability stack for PostgreSQL (with PostGIS), including:

- **Metric collection** via `postgres_exporter`
- **Time-series storage and rules** via `Prometheus`
- **Alerting pipeline** via `Alertmanager`
- **Visualization** via `Grafana`

## 🎯 Goals

- Track WAL activity (`wal_bytes`), replication lag, and BRIN index efficiency
- Detect anomalies and raise alerts with **MTTD < 10 min**
- Visualize and analyze performance over time

---

## 🔧 Services

| Service             | Description |
|---------------------|-------------|
| `db`               | PostgreSQL + PostGIS (the monitored DB) |
| `postgres_exporter`| Exposes metrics from PostgreSQL |
| `prometheus`       | Scrapes and processes metrics, evaluates rules |
| `alertmanager`     | Receives alerts and routes them |
| `grafana`          | Visualizes all metrics and alerts |

---

## 📁 Project Files

| File                           | Purpose |
|--------------------------------|---------|
| `docker-compose.yml`          | Deploys the stack |
| `postgres-queries.yml`        | Custom metrics exposed by postgres_exporter |
| `prometheus.yml`              | Prometheus main config |
| `prometheus-recording.rules.yml` | Precomputed rule expressions |
| `postgres-alerts.yml`         | Alert conditions |
| `alertmanager.yml`            | Alert routing (dummy endpoint for now) |
| `grafana-dashboard.json`      | Ready-to-import Grafana dashboard |

---

## ⚙ How it works

- `postgres_exporter` exposes raw and extended metrics from Postgres.
- Prometheus scrapes these metrics every 30s.
- `recording.rules` calculate derivative data like WAL throughput and cache hit ratios.
- `alerts.yml` defines warning/critical thresholds (e.g., WAL rate, lag > 120s).
- Alerts are sent to Alertmanager and shown in Prometheus UI.
- Grafana queries Prometheus and presents rich dashboards.

---

## 🚀 Getting Started

1. Place all config files in the same folder.
2. Run: `docker compose up -d`
3. Access services:
    - Prometheus: http://localhost:9090
    - Grafana: http://localhost:3000 (default login: `admin` / `admin`)
    - Exporter: http://localhost:9187

4. Import the `grafana-dashboard.json` into Grafana.
5. At the command line, type: `rate(pg_wal_stats_wal_bytes[5m])`

This shows WAL write throughput (bytes per second).


---


## 📊 Recommended Dashboards

- **WAL throughput** (rate in bytes/sec)  
- **Replication lag** (seconds and bytes)  
- **BRIN index hit ratio** (per index)  

### Example
<p align="center">
  <img src="image.png" alt="Grafana Dashboard Example" width="500"/>
</p>



## 📌 Notes

- Assumes database is running on service `db` at port 5432.
- Requires Postgres user with `pg_monitor` role.
- Easily extendable for CPU, memory, connection tracking, etc.
