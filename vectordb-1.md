
---
# Vector DB 1 – pgvector + HNSW + Prometheus

This repo deploys PostgreSQL with **pgvector**, creates a demo **HNSW** index, runs a **42-NN** benchmark, and exposes a **Prometheus** metric via **postgres-exporter**.

## Contents
- `k8s/pgvector-bundle.yaml` – Namespace, ConfigMaps, Service, StatefulSet (`pgvector/pgvector:pg16` + exporter) and a CronJob that runs the benchmark every minute.
- `k8s/prometheus-mini.yaml` – Minimal Prometheus that scrapes the exporter.
- `sql/schema.sql` – Extension/table/index + `bench_nn42_once()`.
- `sql/bench.sql` – Demo data, benchmark runs, and summary query.

## Deploy
```bash
kubectl apply -f k8s/pgvector-bundle.yaml
kubectl -n vectordb rollout status sts/pg

kubectl apply -f k8s/prometheus-mini.yaml
