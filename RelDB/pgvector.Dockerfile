# Extend Bitnami PostgreSQL 16 image with pgvector extension (built from source)
FROM bitnami/postgresql:16

# Switch to root for build tools installation
USER root

# Ensure pg_config points to Bitnami's PostgreSQL and is on PATH
ENV PG_CONFIG=/opt/bitnami/postgresql/bin/pg_config
ENV PATH="/opt/bitnami/postgresql/bin:${PATH}"

# Build pgvector from source against Bitnami PostgreSQL
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential git ca-certificates \
 && git clone --depth 1 https://github.com/pgvector/pgvector.git /tmp/pgvector \
 && make -C /tmp/pgvector \
 && make -C /tmp/pgvector install \
 && rm -rf /var/lib/apt/lists/* /tmp/pgvector

# Back to non-root user as expected by Bitnami
USER 1001

# Init script: create pgvector extension on first DB initialization (new data dir)
COPY initdb/01-enable-pgvector.sql /docker-entrypoint-initdb.d/01-enable-pgvector.sql
