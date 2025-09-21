-- ============================================
-- audio_cls schema (fresh create, PostgreSQL)
-- Includes:
--   - runs
--   - files
--   - file_aggregates (JSON-based head outputs)
--   - indexes
--   - convenience VIEW for 10-class head
-- ============================================

BEGIN;

-- 1) Schema
CREATE SCHEMA IF NOT EXISTS audio_cls;

-- Use schema for subsequent CREATEs
SET search_path TO audio_cls, public;

-- 2) runs: per-run metadata
CREATE TABLE IF NOT EXISTS runs (
  run_id        TEXT PRIMARY KEY,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ,

  model_name    TEXT,
  checkpoint    TEXT,
  head_path     TEXT,
  labels_csv    TEXT,

  window_sec    DOUBLE PRECISION NOT NULL CHECK (window_sec > 0),
  hop_sec       DOUBLE PRECISION NOT NULL CHECK (hop_sec > 0),
  pad_last      BOOLEAN NOT NULL,
  agg           TEXT NOT NULL CHECK (agg IN ('mean','max')),
  topk          INTEGER NOT NULL CHECK (topk >= 1),
  device        TEXT NOT NULL,

  code_version  TEXT,
  notes         TEXT
);

-- 3) files: input file facts
CREATE TABLE IF NOT EXISTS files (
  file_id      BIGSERIAL PRIMARY KEY,
  path         TEXT UNIQUE NOT NULL,
  duration_s   DOUBLE PRECISION CHECK (duration_s IS NULL OR duration_s >= 0),
  sample_rate  INTEGER,
  size_bytes   BIGINT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_audio_cls_files_path
  ON files(path);

-- 4) file_aggregates: final per-file outputs (no per-window rows)
--    JSON keeps the head outputs flexible across different taxonomies.
CREATE TABLE IF NOT EXISTS file_aggregates (
  run_id              TEXT   NOT NULL,
  file_id             BIGINT NOT NULL,

  -- AudioSet (diagnostic) top-K results after aggregation
  audioset_topk_json  JSONB,

  -- Flexible multi-class head probabilities (label -> prob)
  head_probs_json        JSONB,

  -- Final decision with "unknown" fallback
  head_pred_label        TEXT,                -- e.g., one of the 10 labels or 'another'
  head_pred_prob         DOUBLE PRECISION CHECK (head_pred_prob IS NULL OR (head_pred_prob BETWEEN 0 AND 1)),
  head_unknown_threshold DOUBLE PRECISION,    -- the threshold used to decide 'another'
  head_is_another        BOOLEAN,             -- true iff final label is 'another'

  -- Aggregation context
  num_windows            INTEGER CHECK (num_windows IS NULL OR num_windows >= 0),
  agg_mode               TEXT,

  PRIMARY KEY (run_id, file_id),
  FOREIGN KEY (run_id)  REFERENCES runs(run_id)      ON DELETE CASCADE,
  FOREIGN KEY (file_id) REFERENCES files(file_id)    ON DELETE CASCADE
);

-- Helpful indexes
CREATE INDEX IF NOT EXISTS ix_audio_cls_file_agg_run
  ON file_aggregates(run_id);

-- Query frequently by predicted label
CREATE INDEX IF NOT EXISTS ix_audio_cls_file_agg_pred_label
  ON file_aggregates(head_pred_label);

-- JSONB GIN index to enable key/containment queries on probabilities map
CREATE INDEX IF NOT EXISTS ix_audio_cls_file_agg_probs_gin
  ON file_aggregates
  USING GIN (head_probs_json);

-- 5) Convenience VIEW: 10-class columns
--    Maps JSON keys to fixed columns for BI/SQL ease.
DROP VIEW IF EXISTS v_file_aggregates_probs10;
CREATE VIEW v_file_aggregates_probs10 AS
SELECT
  fa.run_id,
  fa.file_id,

  -- per-label probabilities (NULL if key missing in JSON)
  (fa.head_probs_json->>'animal')::double precision          AS head_p_animal,
  (fa.head_probs_json->>'birds')::double precision           AS head_p_birds,
  (fa.head_probs_json->>'fire')::double precision            AS head_p_fire,
  (fa.head_probs_json->>'footsteps')::double precision       AS head_p_footsteps,
  (fa.head_probs_json->>'insects')::double precision         AS head_p_insects,
  (fa.head_probs_json->>'screaming')::double precision       AS head_p_screaming,
  (fa.head_probs_json->>'shotgun')::double precision         AS head_p_shotgun,
  (fa.head_probs_json->>'stormy_weather')::double precision  AS head_p_stormy_weather,
  (fa.head_probs_json->>'streaming_water')::double precision AS head_p_streaming_water,
  (fa.head_probs_json->>'vehicle')::double precision         AS head_p_vehicle,

  -- final decision fields
  fa.head_pred_label,
  fa.head_pred_prob,
  fa.head_unknown_threshold,
  fa.head_is_another,

  -- aggregation context
  fa.num_windows,
  fa.agg_mode
FROM file_aggregates fa;

COMMIT;
