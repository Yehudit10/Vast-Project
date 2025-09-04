# syntax=docker/dockerfile:1
FROM postgis/postgis:16-3.4

# ==== 1) Parameters (keep these names if they match your setup)
ENV POSTGRES_DB=missions_db \
    POSTGRES_USER=missions_user \
    POSTGRES_PASSWORD=pg123 \
    TZ=Asia/Jerusalem

# ==== 2) Install pg_cron for PostgreSQL 16 ====
# Direct attempt (works in most cases). If not found, replace it with the PGDG version below.
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-16-cron && \
    rm -rf /var/lib/apt/lists/*

# ==== 3) Init files (run once when the data directory is empty) ====
COPY build_tables/schema.sql                      /docker-entrypoint-initdb.d/01_schema.sql
COPY build_tables/02_event_logs_partition.sql     /docker-entrypoint-initdb.d/02_event_logs_partition.sql
COPY initdb/03_partitions.sql                     /docker-entrypoint-initdb.d/03_partitions.sql
COPY build_tables/loader.sql                      /docker-entrypoint-initdb.d/04_loader.sql
COPY initdb/04_cron.sql                           /docker-entrypoint-initdb.d/05_cron.sql


EXPOSE 5432

HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
  CMD pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" || exit 1
