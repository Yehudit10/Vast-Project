-- Extended schema v2: adds devices, anomaly catalog, logs, files, and regions.
-- Order matters: referenced tables first.

CREATE EXTENSION IF NOT EXISTS postgis;

-- === Catalogs / reference tables ===

-- Devices catalog
CREATE TABLE IF NOT EXISTS devices (
  device_id text PRIMARY KEY,
  model     text,
  owner     text,
  active    boolean DEFAULT true
);

-- Predefined regions (optional: for missions crossing multiple regions)
CREATE TABLE IF NOT EXISTS regions (
  id    bigserial PRIMARY KEY,
  name  text NOT NULL,
  geom  geometry(Polygon, 4326) NOT NULL
);

-- Types of anomalies
CREATE TABLE IF NOT EXISTS anomaly_types (
  anomaly_type_id serial PRIMARY KEY,
  code        text UNIQUE NOT NULL,
  description text NOT NULL
);

-- === Core entities ===

-- Missions table
CREATE TABLE IF NOT EXISTS missions (
  mission_id   BIGSERIAL PRIMARY KEY,
  start_time   timestamptz NOT NULL,
  end_time     timestamptz,
  area_geom    geometry(Polygon, 4326) NOT NULL,
  CHECK (end_time IS NULL OR end_time > start_time)
);

-- Optional link table if you want explicit mission↔region mapping
CREATE TABLE IF NOT EXISTS mission_regions (
  mission_id bigint NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
  region_id  bigint NOT NULL REFERENCES regions(id)         ON DELETE CASCADE,
  PRIMARY KEY (mission_id, region_id)
);

-- Telemetry points (raw stream)
CREATE TABLE IF NOT EXISTS telemetry (
  id          BIGSERIAL PRIMARY KEY,
  mission_id  BIGINT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
  device_id   text   NOT NULL REFERENCES devices(device_id),
  ts          timestamptz NOT NULL,
  geom        geometry(Point, 4326) NOT NULL,
  altitude    real CHECK (altitude >= 0)
);

-- Per-tile aggregated stats (for heatmaps etc.)
CREATE TABLE IF NOT EXISTS tile_stats (
  id            BIGSERIAL PRIMARY KEY,
  mission_id    BIGINT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
  tile_id       text   NOT NULL,
  anomaly_score real,
  geom          geometry(Polygon, 4326) NOT NULL,
  UNIQUE (mission_id, tile_id)
);

-- Individual anomaly events (point-level)
CREATE TABLE IF NOT EXISTS anomalies (
  anomaly_id       bigserial PRIMARY KEY,
  mission_id       bigint NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
  device_id        text   NOT NULL REFERENCES devices(device_id),
  ts               timestamptz NOT NULL,
  anomaly_type_id  int    NOT NULL REFERENCES anomaly_types(anomaly_type_id),
  severity         real CHECK (severity >= 0),
  details          jsonb,
  geom             geometry(Point,4326)
);

-- Files stored in MinIO (S3-compatible) and referenced here
CREATE TABLE IF NOT EXISTS files (
  file_id      bigserial PRIMARY KEY,
  bucket       text NOT NULL,              -- MinIO bucket name
  object_key   text NOT NULL,              -- path/key inside the bucket
  content_type text,                       -- MIME type (image/jpeg, application/geo+json, ...)
  size_bytes   bigint CHECK (size_bytes >= 0),
  etag         text,                       -- checksum returned by S3/MinIO (MD5/Etag)
  created_at   timestamptz NOT NULL DEFAULT now(),
  mission_id   bigint REFERENCES missions(mission_id) ON DELETE SET NULL,
  device_id    text   REFERENCES devices(device_id)   ON DELETE SET NULL,
  tile_id      text,                        -- optional link to a tile identifier
  footprint    geometry(Polygon,4326),      -- spatial footprint if known
  metadata     jsonb,                       -- arbitrary extra metadata
  UNIQUE (bucket, object_key)
);

-- System / application logs (partitioned by time)
CREATE TABLE IF NOT EXISTS event_logs (
  log_id   bigserial,
  ts       timestamptz NOT NULL,
  level    text NOT NULL CHECK (level IN ('DEBUG','INFO','WARN','ERROR','FATAL')),
  source   text NOT NULL,
  message  text NOT NULL,
  details  jsonb,
  trace_id text,
  user_id  bigint NOT NULL DEFAULT -1,          -- -1 = not triggered by a user
  PRIMARY KEY (log_id, ts)
) PARTITION BY RANGE (ts);


-- === Partitioned parent for telemetry (daily range) ===
CREATE TABLE IF NOT EXISTS telemetry_new (
  mission_id  BIGINT NOT NULL REFERENCES missions(mission_id) ON DELETE CASCADE,
  ts          timestamptz NOT NULL,
  device_id   text NOT NULL REFERENCES devices(device_id),
  geom        geometry(Point,4326) NOT NULL,
  altitude    real,
  PRIMARY KEY (mission_id, ts)
) PARTITION BY RANGE (ts);

CREATE TABLE IF NOT EXISTS users (
  id            SERIAL PRIMARY KEY,
  username      VARCHAR(150) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS service_accounts (
  id         SERIAL PRIMARY KEY,
  name       VARCHAR(150) UNIQUE NOT NULL,
  token      TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id         SERIAL PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token      TEXT UNIQUE NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);



-- === Indexes ===

-- Spatial
CREATE INDEX IF NOT EXISTS ix_missions_area_geom_gist  ON missions   USING GIST (area_geom);
CREATE INDEX IF NOT EXISTS ix_telemetry_geom_gist      ON telemetry  USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_tile_stats_geom_gist     ON tile_stats USING GIST (geom);
CREATE INDEX IF NOT EXISTS ix_files_footprint_gist     ON files      USING GIST (footprint);

-- Time-series
CREATE INDEX IF NOT EXISTS ix_telemetry_ts_brin        ON telemetry  USING BRIN (ts);
CREATE INDEX IF NOT EXISTS ix_anomalies_ts_brin        ON anomalies  USING BRIN (ts);

-- Lookup / filtering
CREATE INDEX IF NOT EXISTS ix_telemetry_mission_ts     ON telemetry (mission_id, ts);
CREATE INDEX IF NOT EXISTS ix_anomalies_mission_ts     ON anomalies (mission_id, ts);
CREATE INDEX IF NOT EXISTS ix_files_mission_created    ON files (mission_id, created_at);

-- JSONB for flexible search
CREATE INDEX IF NOT EXISTS ix_anomalies_details_gin    ON anomalies USING GIN (details);
CREATE INDEX IF NOT EXISTS ix_files_metadata_gin       ON files     USING GIN (metadata);

-- Regions spatial index
CREATE INDEX IF NOT EXISTS ix_regions_geom_gist        ON regions USING GIST (geom);


CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id);
