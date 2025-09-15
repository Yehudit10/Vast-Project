-- Schema + table for rover still-image indexing

CREATE SCHEMA IF NOT EXISTS rover AUTHORIZATION missions_user;

CREATE TABLE IF NOT EXISTS rover.images (
  image_id        text PRIMARY KEY,                 -- unique image identifier
  device_id       text        NOT NULL,             -- rover/camera id
  captured_at     timestamptz NOT NULL,             -- UTC capture time

  lat             double precision NOT NULL CHECK (lat >= -90  AND lat <= 90),
  lon             double precision NOT NULL CHECK (lon >= -180 AND lon <= 180),

  heading_deg     double precision,                 -- [0,360)
  pitch_deg       double precision,
  roll_deg        double precision,
  alt_m           double precision,                 -- camera height (meters)
  fov_deg         double precision,
  gps_accuracy_m  double precision,
  temp_c          double precision,                 -- optional ambient temp

  s3_key          text        NOT NULL,             -- object key in MinIO/S3
  mime_type       text,
  size_bytes      bigint,
  sha256          text,
  exif_present    boolean,
  firmware        text,
  capture_seq     bigint,

  meta_src        text        NOT NULL,             -- 'manifest' | 'telemetry' | 'exif_fallback'
  schema_ver      int         NOT NULL DEFAULT 1,
  source_ts       timestamptz,
  trace_id        text,

  ingested_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_images_device_time ON rover.images (device_id, captured_at);
CREATE INDEX IF NOT EXISTS idx_images_captured_at  ON rover.images (captured_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_images_sha256 ON rover.images (sha256) WHERE sha256 IS NOT NULL;
