# syntax=docker/dockerfile:1
FROM postgis/postgis:16-3.4

# ==== 1) Parameters ====

# ==== 2) Install tools: pg_cron + Python + cron + pgvector ====
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-16-cron \
    postgresql-16-pgvector \
    python3-minimal python3-pip \
    cron \
 && rm -rf /var/lib/apt/lists/*

# ==== 3) Directories for WAL and backups ====
RUN mkdir -p /var/lib/postgresql/wal_archive /var/lib/postgresql/backups && \
    chown -R postgres:postgres /var/lib/postgresql/wal_archive /var/lib/postgresql/backups

# ==== 4) PostgreSQL WAL + pg_cron config ====
RUN echo "wal_level = 'replica'" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "archive_mode = on" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "max_wal_senders = 5" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "archive_timeout = '30s'" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "archive_command = 'cp %p /var/lib/postgresql/wal_archive/%f'" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "log_checkpoints = on" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "shared_preload_libraries = 'pg_cron,vector'" >> /usr/share/postgresql/postgresql.conf.sample && \
    echo "cron.database_name = 'missions_db'" >> /usr/share/postgresql/postgresql.conf.sample

# ==== 5) Copy Python PITR scripts ====
COPY pitr/backup.py       /usr/local/bin/backup.py
COPY pitr/cron_backup.py  /usr/local/bin/cron_backup.py
COPY pitr/recover.py      /usr/local/bin/recover.py
RUN chmod +x /usr/local/bin/*.py


# ==== 6) Init files (run once if PGDATA empty) ====
COPY build_tables/schema.sql                  /docker-entrypoint-initdb.d/01_schema.sql
COPY build_tables/02_event_logs_partition.sql /docker-entrypoint-initdb.d/02_event_logs_partition.sql
COPY initdb/03_partitions.sql                 /docker-entrypoint-initdb.d/03_partitions.sql
COPY build_tables/loader.sql                  /docker-entrypoint-initdb.d/04_loader.sql
COPY initdb/04_cron.sql                       /docker-entrypoint-initdb.d/05_cron.sql

# ==== 7) Replication grants ====
RUN echo "ALTER ROLE missions_user WITH REPLICATION;" > /docker-entrypoint-initdb.d/00_grant_replication.sql

# ==== 8) Cron job (nightly backup 03:00) ====
RUN echo "0 3 * * * postgres python3 /usr/local/bin/cron_backup.py" >> /etc/crontab

EXPOSE 5432

# ==== 9) Healthcheck ====
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
  CMD pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" || exit 1

# ==== 10) Final CMD: start cron + Postgres + initial backup ====
CMD ["bash", "-c", "service cron start && \
chown -R postgres:postgres /var/lib/postgresql/wal_archive /var/lib/postgresql/backups && \
docker-entrypoint.sh postgres & \
until pg_isready -U \"$POSTGRES_USER\" -d \"$POSTGRES_DB\"; do sleep 2; done; \
su - postgres -c 'python3 /usr/local/bin/backup.py' && wait -n"]
