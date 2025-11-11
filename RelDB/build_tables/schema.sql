-- Extended schema v2: adds devices, anomaly catalog, logs, files, and regions.
-- Order matters: referenced tables first.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS vector;

-- === Catalogs / reference tables ===

-- Devices catalog
CREATE TABLE IF NOT EXISTS devices (
  device_id text PRIMARY KEY,
  model     text,
  owner     text,
  active    boolean DEFAULT true,
  location_lat DOUBLE PRECISION,
  location_lon DOUBLE PRECISION
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

--Types of leaf diseases
CREATE TABLE IF NOT EXISTS leaf_disease_types (
    id   SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);
-- === Core entities ===

CREATE TABLE IF NOT EXISTS leaf_reports (
    id                     BIGSERIAL PRIMARY KEY,
    device_id              TEXT NOT NULL REFERENCES devices(device_id),
    leaf_disease_type_id   INT  NOT NULL REFERENCES leaf_disease_types(id),
    ts                     TIMESTAMPTZ NOT NULL,
    confidence             DOUBLE PRECISION CHECK (confidence >= 0 AND confidence <= 1),
    sick                   BOOLEAN NOT NULL
);


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

CREATE TABLE IF NOT EXISTS clients (
  schedule_id BIGSERIAL PRIMARY KEY,
  client_id   BIGINT NOT NULL,
  team        VARCHAR(150),
  cron_expr   TEXT,
  active_days TEXT,
  time_window TEXT,
  last_updated TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- CREATE TABLE IF NOT EXISTS ultrasonic_plant_predictions (
--     id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
--     predicted_class TEXT NOT NULL,
--     confidence FLOAT NOT NULL,
--     -- status TEXT NOT NULL,
--     prediction_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );
CREATE TABLE IF NOT EXISTS ultrasonic_plant_predictions (
  id               BIGSERIAL PRIMARY KEY,
  file             TEXT,
  predicted_class  TEXT,
  confidence       DOUBLE PRECISION,
  watering_status  TEXT,
  status           TEXT,
  prediction_time  TIMESTAMPTZ DEFAULT now()
);

-- service_accounts
CREATE TABLE IF NOT EXISTS public.service_accounts (
    id          integer GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name        varchar(150) NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    token_hash  text NOT NULL
);


CREATE TABLE IF NOT EXISTS refresh_tokens (
  id         SERIAL PRIMARY KEY,
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token      TEXT UNIQUE NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);



--- === Embeddings table for vector data (e.g. image embeddings) ===
CREATE TABLE IF NOT EXISTS embeddings (
  id BIGSERIAL PRIMARY KEY,
  vec vector(784)
);
CREATE TABLE IF NOT EXISTS training_runs (
    id BIGSERIAL PRIMARY KEY,
    run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    backbone TEXT NOT NULL,
    image_size INT NOT NULL,
    num_epochs INT NOT NULL,
    train_split NUMERIC(4,3) NOT NULL,
    top1_acc NUMERIC(5,4) NOT NULL,
    best_top1_acc NUMERIC(5,4) NOT NULL,
    artifacts_bucket TEXT NOT NULL,
    artifacts_prefix TEXT NOT NULL,
    labels_object TEXT NOT NULL,
    best_ckpt_object TEXT NOT NULL,
    metrics_object TEXT NOT NULL,
    cm_object TEXT NOT NULL,
    seed INT NOT NULL
);

-- Inferenceevent_logs_sensors, instead of Inference logs:
CREATE TABLE IF NOT EXISTS inference_logs (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    model_backbone TEXT NOT NULL,
    image_size INT NOT NULL,
    fruit_type TEXT NOT NULL,
    score NUMERIC(5,4) NOT NULL,
    latency_ms NUMERIC(8,3) NOT NULL,
    client_ip TEXT,
    error TEXT,
    image_url TEXT
);

-- Ripeness predictions table
CREATE TABLE IF NOT EXISTS ripeness_predictions (
    id BIGSERIAL PRIMARY KEY,
    inference_log_id BIGINT NOT NULL REFERENCES inference_logs(id) ON DELETE CASCADE,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ripeness_label TEXT NOT NULL CHECK (ripeness_label IN ('ripe', 'unripe', 'overripe')),
    ripeness_score DOUBLE PRECISION NOT NULL,
    model_name TEXT NOT NULL,
    run_id UUID NOT NULL,
    device_id TEXT REFERENCES devices(device_id),
    UNIQUE (inference_log_id)
);

-- Create indexes for ripeness_predictions
CREATE INDEX IF NOT EXISTS ix_ripeness_inflog ON ripeness_predictions(inference_log_id);
CREATE INDEX IF NOT EXISTS ix_ripeness_ts ON ripeness_predictions(ts);
CREATE INDEX IF NOT EXISTS ix_ripeness_device ON ripeness_predictions(device_id);
CREATE INDEX IF NOT EXISTS ix_ripeness_run ON ripeness_predictions(run_id);
CREATE INDEX IF NOT EXISTS ix_leaf_reports_ts_brin ON leaf_reports USING BRIN (ts);
CREATE INDEX IF NOT EXISTS ix_leaf_reports_device_ts ON leaf_reports (device_id, ts);
CREATE INDEX IF NOT EXISTS ix_leaf_reports_type_ts ON leaf_reports (leaf_disease_type_id, ts);

-- Weekly ripeness rollups table
CREATE TABLE IF NOT EXISTS ripeness_weekly_rollups_ts (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    fruit_type TEXT NOT NULL,
    device_id TEXT REFERENCES devices(device_id),
    run_id UUID NOT NULL,
    cnt_total INTEGER NOT NULL,
    cnt_ripe INTEGER NOT NULL,
    cnt_unripe INTEGER NOT NULL,
    cnt_overripe INTEGER NOT NULL,
    pct_ripe DOUBLE PRECISION NOT NULL
);

-- Create indexes for ripeness_weekly_rollups_ts
CREATE INDEX IF NOT EXISTS ix_rwrt_ts ON ripeness_weekly_rollups_ts(ts);
CREATE INDEX IF NOT EXISTS ix_rwrt_fruit_ts ON ripeness_weekly_rollups_ts(fruit_type, ts);
CREATE INDEX IF NOT EXISTS ix_rwrt_device ON ripeness_weekly_rollups_ts(device_id);
CREATE INDEX IF NOT EXISTS ix_rwrt_run ON ripeness_weekly_rollups_ts(run_id);

-- Sensor event logs table.
CREATE TABLE IF NOT EXISTS event_logs_sensors(
    id         bigserial PRIMARY KEY,
    device_id  text        NOT NULL REFERENCES devices(device_id),
    issue_type text        NOT NULL,
    severity   text        NOT NULL CHECK (severity IN ('info','warn','error','critical')),
    start_ts   timestamptz NOT NULL DEFAULT now(),
    end_ts     timestamptz NULL,
    details    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT event_logs_sensors_end_after_start
        CHECK (end_ts IS NULL OR end_ts >= start_ts)
);



CREATE TABLE IF NOT EXISTS sensors (
  id SERIAL PRIMARY KEY,
  sensor_name TEXT UNIQUE NOT NULL,
  sensor_type TEXT NOT NULL,
  owner_name TEXT,
  location_lat DOUBLE PRECISION,
  location_lon DOUBLE PRECISION,
  install_date TIMESTAMP DEFAULT NOW(),
  status TEXT DEFAULT 'active',
  description TEXT,
  last_maintenance TIMESTAMP
);
CREATE TABLE IF NOT EXISTS public.sensor_anomalies (
    id BIGSERIAL PRIMARY KEY,
    plant_id INT NOT NULL,
    sensor VARCHAR(64) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    zone VARCHAR(128),
    result JSONB NOT NULL,           
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);



CREATE TABLE IF NOT EXISTS public.sensor_zone_stats (
    id BIGSERIAL PRIMARY KEY,
    zone VARCHAR(128) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    count INT NOT NULL,
    mean DOUBLE PRECISION,
    median DOUBLE PRECISION,
    min DOUBLE PRECISION,
    max DOUBLE PRECISION,
    std DOUBLE PRECISION,
    anomalies INT,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

--- === Soil moisture irrigation tables ===

CREATE TABLE IF NOT EXISTS soil_moisture_events (
  id SERIAL PRIMARY KEY,
  zone_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  dry_ratio REAL NOT NULL,
  decision TEXT NOT NULL,
  confidence REAL NOT NULL,
  patch_count INT NOT NULL,
  idempotency_key TEXT NOT NULL,
  extra JSONB DEFAULT '{}'::jsonb
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idem ON soil_moisture_events (idempotency_key);

CREATE TABLE IF NOT EXISTS irrigation_schedule (
  zone_id TEXT PRIMARY KEY,
  next_run_at TIMESTAMPTZ NOT NULL,
  duration_min INT NOT NULL,
  updated_by TEXT NOT NULL,
  update_reason TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS irrigation_schedule_audit (
  id SERIAL PRIMARY KEY,
  zone_id TEXT NOT NULL,
  prev_next_run_at TIMESTAMPTZ,
  prev_duration_min INT,
  next_run_at TIMESTAMPTZ NOT NULL,
  duration_min INT NOT NULL,
  updated_by TEXT NOT NULL,
  update_reason TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (

    -- Required fields
    alert_id TEXT PRIMARY KEY,
    alert_type TEXT,
    device_id TEXT,
    started_at TIMESTAMPTZ,

    -- Optional / dynamic fields
    ended_at TIMESTAMPTZ,
    confidence DOUBLE PRECISION,
    area TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    severity INT DEFAULT 1,
    image_url TEXT,
    vod TEXT,
    hls TEXT,

    -- Acknowledgment field
    ack BOOLEAN DEFAULT FALSE,  -- TRUE when the alert was acknowledged

    -- Flexible metadata for anything else
    meta JSONB,

    -- System fields
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- === Task thresholds (enum + table) ===
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'task_type_enum') THEN
        CREATE TYPE task_type_enum AS ENUM (
            'ripeness',    
            'disease',    
            'size',        
            'color',       
            'quality'      
        );
    END IF;
END$$;

CREATE TABLE IF NOT EXISTS task_thresholds (
    threshold_id SERIAL PRIMARY KEY,                 
    task       task_type_enum NOT NULL,           
    label      TEXT NOT NULL DEFAULT '',         
    threshold  NUMERIC(6,4) NOT NULL CHECK (threshold >= 0 AND threshold <= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT,
    CONSTRAINT ux_task_thresholds_task_label UNIQUE (task, label)
);

CREATE TABLE public.image_new_aerial_connections (
  id BIGSERIAL PRIMARY KEY,
  file_name VARCHAR(255),
  key TEXT,
  linked_time TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.aerial_images_metadata (
    id SERIAL PRIMARY KEY,

    -- File and drone metadata
    file_name TEXT NOT NULL,
    drone_id TEXT NOT NULL,
    capture_time TIMESTAMP WITH TIME ZONE NOT NULL,

    -- Raw JSON as received (latitude/longitude)
    gis_origin JSONB NOT NULL,

    -- Geometry point auto-generated from JSON
    geom_point geometry(Point, 4326)
        GENERATED ALWAYS AS (
            ST_SetSRID(
                ST_MakePoint(
                    (gis_origin->>'longitude')::double precision,
                    (gis_origin->>'latitude')::double precision
                ),
                4326
            )
        ) STORED,

    -- Flight attributes
    altitude_m DOUBLE PRECISION,
    done BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_aerial_geom_point_gist
ON public.aerial_images_metadata USING GIST (geom_point);


CREATE TABLE IF NOT EXISTS public.aerial_image_object_detections (
    id SERIAL PRIMARY KEY,
    img_key TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    bbox_x1 DOUBLE PRECISION NOT NULL,
    bbox_y1 DOUBLE PRECISION NOT NULL,
    bbox_x2 DOUBLE PRECISION NOT NULL,
    bbox_y2 DOUBLE PRECISION NOT NULL,
    detected_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_image_object_detections_key
    ON public.aerial_image_object_detections (img_key);


CREATE TABLE IF NOT EXISTS public.aerial_image_anomaly_detections (
    id SERIAL PRIMARY KEY,
    img_key TEXT NOT NULL,
    label TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    bbox_x1 DOUBLE PRECISION NOT NULL,
    bbox_y1 DOUBLE PRECISION NOT NULL,
    bbox_x2 DOUBLE PRECISION NOT NULL,
    bbox_y2 DOUBLE PRECISION NOT NULL,
    detected_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_image_anomaly_detections_key
    ON public.aerial_image_anomaly_detections (img_key);


CREATE TABLE IF NOT EXISTS public.aerial_images_complete_metadata (
    id SERIAL PRIMARY KEY,
    file_name TEXT NOT NULL,
    device_id TEXT NOT NULL,
    gis_origin JSONB,
    gis geometry(Point, 4326)
        GENERATED ALWAYS AS (
            ST_SetSRID(
                ST_MakePoint(
                    (gis_origin->>'longitude')::double precision,
                    (gis_origin->>'latitude')::double precision
                ),
                4326
            )
        ) STORED,
    img_key TEXT NOT NULL UNIQUE,
    timestamp_utc TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aerial_metadata_device_id
    ON public.aerial_images_complete_metadata (device_id);

CREATE INDEX IF NOT EXISTS idx_aerial_metadata_timestamp
    ON public.aerial_images_complete_metadata (timestamp_utc);

CREATE INDEX IF NOT EXISTS idx_aerial_metadata_gis
    ON public.aerial_images_complete_metadata USING GIST (gis);


CREATE TABLE IF NOT EXISTS public.field_polygons (
    id SERIAL PRIMARY KEY,
    gis geometry(Point, 4326) NOT NULL,
    boundary geometry(Polygon, 4326) NOT NULL,
    area_sq_m DOUBLE PRECISION GENERATED ALWAYS AS (
        ST_Area(geography(boundary))
    ) STORED,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_field_polygons_gis
    ON public.field_polygons USING GIST (gis);


CREATE TABLE IF NOT EXISTS public.aerial_image_segmentation (
    id SERIAL PRIMARY KEY,
    img_key TEXT NOT NULL,
    mask_path TEXT,
    other FLOAT DEFAULT 0,
    bareland FLOAT DEFAULT 0,
    rangeland FLOAT DEFAULT 0,
    developed_space FLOAT DEFAULT 0,
    road FLOAT DEFAULT 0,
    tree FLOAT DEFAULT 0,
    water FLOAT DEFAULT 0,
    agriculture FLOAT DEFAULT 0,
    building FLOAT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_segmentation_img_key
    ON public.aerial_image_segmentation (img_key);


CREATE TABLE public.sound_new_sounds_connections (
  id BIGSERIAL PRIMARY KEY,
  file_name VARCHAR(255),
  key TEXT,
  linked_time TIMESTAMPTZ
);

CREATE TABLE public.sound_new_plants_connections (
  id BIGSERIAL PRIMARY KEY,
  file_name VARCHAR(255),
  key TEXT,
  linked_time TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_task_thresholds_task ON task_thresholds (task);
CREATE INDEX IF NOT EXISTS ix_task_thresholds_updated_at ON task_thresholds (updated_at);

CREATE TABLE IF NOT EXISTS public.sounds_metadata (
  id              BIGSERIAL PRIMARY KEY,
  file_name       TEXT        NOT NULL,
  device_id       TEXT        NOT NULL REFERENCES public.devices(device_id),
  capture_time    TIMESTAMPTZ NOT NULL,                       -- UTC
  duration_sec    DOUBLE PRECISION CHECK (duration_sec >= 0), -- non-negative
  done            BOOLEAN     NOT NULL DEFAULT FALSE,
  sample_rate_hz  INTEGER     CHECK (sample_rate_hz > 0),
  channels        SMALLINT    CHECK (channels > 0),
  content_type    TEXT,
  gis_origin      geometry(Point, 4326) NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- optional: prevent duplicates per device & time
  CONSTRAINT ux_sounds_dev_time UNIQUE (device_id, capture_time)
);

-- Indexes for sounds_metadata
CREATE INDEX IF NOT EXISTS ix_sounds_meta_ts_brin
  ON public.sounds_metadata USING BRIN (capture_time);

CREATE INDEX IF NOT EXISTS ix_sounds_meta_device_time
  ON public.sounds_metadata (device_id, capture_time);

CREATE INDEX IF NOT EXISTS ix_sounds_meta_geom_gist
  ON public.sounds_metadata USING GIST (gis_origin);

CREATE INDEX IF NOT EXISTS ix_sounds_meta_file_name
  ON public.sounds_metadata (file_name);

CREATE INDEX IF NOT EXISTS ix_sounds_meta_created_brin
  ON public.sounds_metadata USING BRIN (created_at);
  

CREATE TABLE IF NOT EXISTS public.sounds_ultra_metadata (
  id              BIGSERIAL PRIMARY KEY,
  file_name       TEXT        NOT NULL,
  device_id       TEXT        NOT NULL REFERENCES public.devices(device_id),
  capture_time    TIMESTAMPTZ NOT NULL,                       -- UTC
  duration_sec    DOUBLE PRECISION CHECK (duration_sec >= 0),
  done            BOOLEAN     NOT NULL DEFAULT FALSE,
  sample_rate_hz  INTEGER     CHECK (sample_rate_hz > 0),
  channels        SMALLINT    CHECK (channels > 0),
  content_type    TEXT,
  gis_origin      geometry(Point, 4326) NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- optional: prevent duplicates per device & time
  CONSTRAINT ux_ultra_sounds_dev_time UNIQUE (device_id, capture_time)
);

-- Indexes for sounds_ultra_metadata
CREATE INDEX IF NOT EXISTS ix_ultra_sounds_meta_ts_brin
  ON public.sounds_ultra_metadata USING BRIN (capture_time);

CREATE INDEX IF NOT EXISTS ix_ultra_sounds_meta_device_time
  ON public.sounds_ultra_metadata (device_id, capture_time);

CREATE INDEX IF NOT EXISTS ix_ultra_sounds_meta_geom_gist
  ON public.sounds_ultra_metadata USING GIST (gis_origin);

CREATE INDEX IF NOT EXISTS ix_ultra_sounds_meta_file_name
  ON public.sounds_ultra_metadata (file_name);

CREATE INDEX IF NOT EXISTS ix_ultra_sounds_meta_created_brin
  ON public.sounds_ultra_metadata USING BRIN (created_at);


-- === Indexes for performance optimization ===


CREATE INDEX IF NOT EXISTS ix_sensor_anomalies_ts_brin
    ON public.sensor_anomalies USING BRIN (ts);

CREATE INDEX IF NOT EXISTS ix_sensor_anomalies_zone
    ON public.sensor_anomalies (zone);

CREATE INDEX IF NOT EXISTS ix_sensor_anomalies_sensor
    ON public.sensor_anomalies (sensor);


CREATE INDEX IF NOT EXISTS ix_sensor_zone_stats_zone_window
    ON public.sensor_zone_stats (zone, window_start, window_end);

CREATE INDEX IF NOT EXISTS ix_sensor_zone_stats_anomalies
    ON public.sensor_zone_stats (anomalies);
CREATE INDEX IF NOT EXISTS ix_sensors_name ON sensors (sensor_name);
CREATE INDEX IF NOT EXISTS ix_sensors_type ON sensors (sensor_type);
CREATE INDEX IF NOT EXISTS ix_sensors_status ON sensors (status);
CREATE INDEX IF NOT EXISTS ix_sensors_location ON sensors (location_lat, location_lon);

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


-- Vector index for embeddings (using HNSW)
CREATE INDEX IF NOT EXISTS idx_embeddings_vec_hnsw    ON embeddings USING hnsw (vec vector_l2_ops)  WITH (m=4, ef_construction=10);

CREATE INDEX IF NOT EXISTS ix_users_username ON users (username);
CREATE INDEX IF NOT EXISTS ix_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_service_accounts_name ON public.service_accounts (name);
CREATE INDEX IF NOT EXISTS ix_service_accounts_id ON public.service_accounts (id);

CREATE INDEX IF NOT EXISTS idx_infer_ts ON inference_logs (ts);
CREATE INDEX IF NOT EXISTS idx_infer_fruit ON inference_logs (fruit_type);

-- Sensors logs
CREATE INDEX IF NOT EXISTS ix_event_logs_sensors_device_start ON event_logs_sensors (device_id, start_ts);
CREATE INDEX IF NOT EXISTS ix_event_logs_sensors_start_brin   ON event_logs_sensors USING BRIN (start_ts);
CREATE INDEX IF NOT EXISTS ix_event_logs_sensors_details_gin  ON event_logs_sensors USING GIN (details jsonb_path_ops);




/* ===========================
   ADDED: Incidents schema v1
   =========================== */

-- =========================
-- Incidents: one event row
-- =========================
-- anomaly_type_id   int    REFERENCES anomaly_types(anomaly_type_id) ON DELETE SET NULL, 
CREATE TABLE IF NOT EXISTS incidents (                                                                                              -- [ADDED]
  incident_id       uuid PRIMARY KEY,                                                                                               -- [ADDED]
  mission_id        bigint REFERENCES missions(mission_id)           ON DELETE SET NULL,                                            -- [ADDED]
  device_id         text   REFERENCES devices(device_id)             ON DELETE SET NULL,                                            -- [ADDED]
  anomaly           text,                                                                                                                      -- [ADDED]
  started_at        timestamptz NOT NULL,                                                                                            -- [ADDED]
  ended_at          timestamptz,                                                                                                     -- [ADDED]
  duration_sec      double precision,                                                                                                 -- [ADDED]
  frame_start       int,                                                                                                              -- [ADDED]
  frame_end         int,                                                                                                              -- [ADDED]
                                                                                                                                    -- [ADDED]
  -- NEW: aggregate severity (mean tracks/frame over the incident)                                                                    -- [ADDED]
  severity          real,                                                                                                             -- [ADDED]
                                                                                                                                    -- [ADDED]
  -- image-space ROI; keep flexible                                                                                                   -- [ADDED]
  roi_pixels        jsonb,                                                                                                            -- [ADDED]
  -- optional map footprint (camera frustum, area of interest, etc.)                                                                  -- [ADDED]
  footprint         geometry(Polygon,4326),                                                                                           -- [ADDED]
                                                                                                                                    -- [ADDED]
  -- canonical media for playback (referencing your existing files table)                                                             -- [ADDED]
  clip_file_id      bigint REFERENCES files(file_id)   ON DELETE SET NULL,                                                            -- [ADDED]
  poster_file_id    bigint REFERENCES files(file_id)   ON DELETE SET NULL,                                                            -- [ADDED]
                                                                                                                                    -- [ADDED]
  -- optional pre-baked UI timeline (array of {frame,ts,box,conf,url,...})                                                            -- [ADDED]
  frames_manifest   jsonb,                                                                                                            -- [ADDED]
  is_real           boolean,
  ack     boolean DEFAULT false,                                                                                                       -- [ADDED]
  meta              jsonb DEFAULT '{}'::jsonb                                                                                        -- [ADDED]
);                                                                                                                                  -- [ADDED]

-- Helpful indexes                                                                                                                  -- [ADDED]
CREATE INDEX IF NOT EXISTS ix_incidents_device_time  ON incidents (device_id, started_at DESC);                                      -- [ADDED]
CREATE INDEX IF NOT EXISTS ix_incidents_mission_time ON incidents (mission_id, started_at DESC);                                     -- [ADDED]

-- ==========================================
-- Per-frame timeline: one row per frame
-- Store ALL detections (bbox + conf + track_id) in JSONB
-- ==========================================
DROP TABLE IF EXISTS incident_frames CASCADE;                                                                                        -- [ADDED]

CREATE TABLE incident_frames (                                                                                                       -- [ADDED]
  incident_id   uuid NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,                                                   -- [ADDED]
  frame_idx     int  NOT NULL,                                                                                                       -- [ADDED]
  ts            timestamptz NOT NULL,                                                                                                -- [ADDED]
                                                                                                                                    -- [ADDED]
  -- List of detection objects:                                                                                                       -- [ADDED]
  -- [{"x1":int,"y1":int,"x2":int,"y2":int,"conf":float|null,"track_id":int|null}, ...]                                               -- [ADDED]
  detections    jsonb NOT NULL DEFAULT '[]'::jsonb,                                                                                  -- [ADDED]
                                                                                                                                    -- [ADDED]
  cls_name      text,                                                                                                                -- [ADDED]
  cls_id        text,                                                                                                                -- [ADDED]
                                                                                                                                    -- [ADDED]
  -- Annotated (or raw) frame stored in files                                                                                         -- [ADDED]
  file_id       bigint REFERENCES files(file_id) ON DELETE SET NULL,                                                                 -- [ADDED]
                                                                                                                                    -- [ADDED]
  meta          jsonb DEFAULT '{}'::jsonb,                                                                                           -- [ADDED]
  PRIMARY KEY (incident_id, frame_idx)                                                                                               -- [ADDED]
);                                                                                                                                  -- [ADDED]

-- Useful indexes                                                                                                                    -- [ADDED]
CREATE INDEX IF NOT EXISTS ix_incident_frames_ts                                                                                     -- [ADDED]
  ON incident_frames (incident_id, ts);                                                                                              -- [ADDED]

-- JSONB GIN index for detection queries (by bbox/conf/track_id)                                                                     -- [ADDED]
CREATE INDEX IF NOT EXISTS ix_incident_frames_detections_gin                                                                         -- [ADDED]
  ON incident_frames USING GIN (detections jsonb_path_ops);                                                                          -- [ADDED]

-- (Optional) denormalized count for quick metrics                                                                                    -- [ADDED]
ALTER TABLE incident_frames                                                                                                          -- [ADDED]
  ADD COLUMN IF NOT EXISTS num_tracks int                                                                                            -- [ADDED]
  GENERATED ALWAYS AS (jsonb_array_length(detections)) STORED;                                                                       -- [ADDED]

-- CREATE INDEX IF NOT EXISTS ix_alerts_entity_rule ON public.alerts(entity_id, rule);
-- CREATE INDEX IF NOT EXISTS ix_alerts_status ON public.alerts(status);

-- ============================================
-- 🔹 MISSING TABLES AND INDEXES FROM FIRST SCHEMA
-- ============================================

-- Devices sensor mapping
CREATE TABLE IF NOT EXISTS devices_sensor (
  id           TEXT UNIQUE NOT NULL,
  plant_id     INT NOT NULL,
  sensor_type  TEXT NOT NULL,
  PRIMARY KEY (plant_id, id)
);

-- Zones table (for linking sensors to geographic areas)
CREATE TABLE IF NOT EXISTS public.zones (
    id SERIAL PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    geom geometry(POLYGON, 4326) NOT NULL
);

-- Extended sensors table with all environmental metrics
DROP TABLE IF EXISTS public.sensors CASCADE;
CREATE TABLE IF NOT EXISTS public.sensors (
  id SERIAL PRIMARY KEY,
  sensor_name TEXT UNIQUE NOT NULL,
  sensor_type TEXT NOT NULL,
  owner_name TEXT,
  location_lat DOUBLE PRECISION,
  location_lon DOUBLE PRECISION,
  install_date TIMESTAMP DEFAULT NOW(),
  status TEXT DEFAULT 'active',
  description TEXT,
  last_maintenance TIMESTAMP,
  value DOUBLE PRECISION,
  humidity DOUBLE PRECISION,
  temperature DOUBLE PRECISION,
  ph DOUBLE PRECISION,
  rainfall DOUBLE PRECISION,
  soil_moisture DOUBLE PRECISION,
  co2_concentration DOUBLE PRECISION,
  n DOUBLE PRECISION,
  p DOUBLE PRECISION,
  k DOUBLE PRECISION,
  label TEXT,
  timestamp TIMESTAMPTZ NOT NULL,
  msg_type TEXT,
  plant_id INT,
  soil_type INT,
  sunlight_exposure DOUBLE PRECISION,
  wind_speed DOUBLE PRECISION,
  organic_matter DOUBLE PRECISION,
  irrigation_frequency DOUBLE PRECISION,
  crop_density DOUBLE PRECISION,
  pest_pressure DOUBLE PRECISION,
  fertilizer_usage DOUBLE PRECISION,
  growth_stage INT,
  urban_area_proximity DOUBLE PRECISION,
  water_source_type INT,
  frost_risk DOUBLE PRECISION,
  water_usage_efficiency DOUBLE PRECISION
);

-- Sensor anomalies table with full structure and JSONB result
DROP TABLE IF EXISTS public.sensor_anomalies CASCADE;
CREATE TABLE IF NOT EXISTS public.sensor_anomalies (
    id BIGSERIAL PRIMARY KEY,
    idSensor INT NOT NULL,
    plant_id INT NOT NULL,
    sensor VARCHAR(64) NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    value DOUBLE PRECISION,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    zone VARCHAR(128),
    result JSONB NOT NULL,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Sensors anomalies modal (aggregated anomaly detection model)
CREATE TABLE IF NOT EXISTS public.sensors_anomalies_modal (
    id           BIGSERIAL PRIMARY KEY,
    sensor_id    TEXT NOT NULL REFERENCES sensors(sensor_name) ON DELETE CASCADE,
    ts           TIMESTAMPTZ NOT NULL,
    anomaly      REAL NOT NULL CHECK (anomaly >= 0),
    inserted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Updated event_logs_sensors referencing devices_sensor
DROP TABLE IF EXISTS event_logs_sensors CASCADE;
CREATE TABLE IF NOT EXISTS event_logs_sensors(
    id         bigserial PRIMARY KEY,
    device_id  TEXT     NOT NULL REFERENCES devices_sensor(id),
    issue_type text        NOT NULL,
    severity   text        NOT NULL CHECK (severity IN ('info','warn','error','critical')),
    start_ts   timestamptz NOT NULL DEFAULT now(),
    end_ts     timestamptz NULL,
    details    jsonb       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT event_logs_sensors_end_after_start
        CHECK (end_ts IS NULL OR end_ts >= start_ts)
);

-- Sensor zone statistics (for per-region summaries)
CREATE TABLE IF NOT EXISTS public.sensor_zone_stats (
    id BIGSERIAL PRIMARY KEY,
    zone VARCHAR(128) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    count INT NOT NULL,
    mean DOUBLE PRECISION,
    median DOUBLE PRECISION,
    min DOUBLE PRECISION,
    max DOUBLE PRECISION,
    std DOUBLE PRECISION,
    anomalies INT,
    inserted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================
-- 🔹 INDEXES FOR SENSOR TABLES
-- ============================================

CREATE INDEX IF NOT EXISTS ix_sensors_anomalies_modal_sensor_ts
    ON sensors_anomalies_modal (sensor_id, ts);

CREATE INDEX IF NOT EXISTS ix_sensor_anomalies_ts_brin
    ON public.sensor_anomalies USING BRIN (ts);

CREATE INDEX IF NOT EXISTS ix_sensor_anomalies_zone
    ON public.sensor_anomalies (zone);

CREATE INDEX IF NOT EXISTS ix_sensor_anomalies_sensor
    ON public.sensor_anomalies (sensor);

CREATE INDEX IF NOT EXISTS ix_sensor_zone_stats_zone_window
    ON public.sensor_zone_stats (zone, window_start, window_end);

CREATE INDEX IF NOT EXISTS ix_sensor_zone_stats_anomalies
    ON public.sensor_zone_stats (anomalies);

CREATE INDEX IF NOT EXISTS ix_sensors_name ON sensors (sensor_name);
CREATE INDEX IF NOT EXISTS ix_sensors_type ON sensors (sensor_type);
CREATE INDEX IF NOT EXISTS ix_sensors_status ON sensors (status);
CREATE INDEX IF NOT EXISTS ix_sensors_location ON sensors (location_lat, location_lon);
