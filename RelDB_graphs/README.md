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

## Notes

- Default credentials:
  - postgres / `PgAdmin!ChangeMe123`
  - missions_user / `Missions!ChangeMe123`
- Configuration files:
  - `prometheus.yml`, `prometheus-recording.rules.yml`, `postgres-alerts.yml`
  - `grafana-datasource.yml`, `grafana-dashboards.yml`, `grafana-dashboard.json`
- All SQL init scripts under `/work/initdb` are automatically applied in order.

Enjoy your graphs! 🎉
