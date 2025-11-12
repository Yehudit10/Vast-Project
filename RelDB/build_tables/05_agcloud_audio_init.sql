-- agcloud_audio initialization (schema + tables + indexes + 11-class view)

BEGIN;

-- 1) Schema
CREATE SCHEMA IF NOT EXISTS agcloud_audio;

-- Use schema for subsequent CREATEs
SET search_path TO agcloud_audio, public;

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

-- 3) file_aggregates: final per-file outputs; references public.sounds_new_sounds_connections(id)
CREATE TABLE IF NOT EXISTS file_aggregates (
  run_id                 TEXT   NOT NULL,
  file_id                BIGINT NOT NULL,

  -- Flexible multi-class head probabilities (label -> prob)
  head_probs_json        JSONB,

  -- Final decision with "unknown" fallback
  head_pred_label        TEXT,
  head_pred_prob         DOUBLE PRECISION CHECK (head_pred_prob IS NULL OR (head_pred_prob BETWEEN 0 AND 1)),
  head_unknown_threshold DOUBLE PRECISION,
  head_is_another        BOOLEAN,

  -- Aggregation context
  num_windows            INTEGER CHECK (num_windows IS NULL OR num_windows >= 0),
  agg_mode               TEXT,

  -- Performance metric (ms)
  processing_ms          INTEGER CHECK (processing_ms IS NULL OR processing_ms >= 0),

  PRIMARY KEY (run_id, file_id),
  FOREIGN KEY (run_id)  REFERENCES runs(run_id)        ON DELETE CASCADE,
  FOREIGN KEY (file_id) REFERENCES public.sound_new_sounds_connections(id) ON DELETE CASCADE
);

-- Helpful indexes
CREATE INDEX ix_agcloud_file_agg_run
  ON file_aggregates(run_id);

CREATE INDEX ix_agcloud_file_agg_pred_label
  ON file_aggregates(head_pred_label);

-- JSONB GIN index to enable key/containment queries on probabilities map
CREATE INDEX ix_agcloud_file_agg_probs_gin
  ON file_aggregates USING GIN (head_probs_json);

-- 4) Views
DROP VIEW IF EXISTS v_file_aggregates_probs10;
DROP VIEW IF EXISTS v_file_aggregates_probs11;

-- 11-class columns view (current head taxonomy)
CREATE VIEW v_file_aggregates_probs11 AS
SELECT
  fa.run_id,
  fa.file_id,
  (fa.head_probs_json->>'predatory_animals')::double precision      AS head_p_predatory_animals,
  (fa.head_probs_json->>'non_predatory_animals')::double precision  AS head_p_non_predatory_animals,
  (fa.head_probs_json->>'birds')::double precision                   AS head_p_birds,
  (fa.head_probs_json->>'fire')::double precision                    AS head_p_fire,
  (fa.head_probs_json->>'footsteps')::double precision               AS head_p_footsteps,
  (fa.head_probs_json->>'insects')::double precision                 AS head_p_insects,
  (fa.head_probs_json->>'screaming')::double precision               AS head_p_screaming,
  (fa.head_probs_json->>'shotgun')::double precision                 AS head_p_shotgun,
  (fa.head_probs_json->>'stormy_weather')::double precision          AS head_p_stormy_weather,
  (fa.head_probs_json->>'streaming_water')::double precision         AS head_p_streaming_water,
  (fa.head_probs_json->>'vehicle')::double precision                 AS head_p_vehicle,
  fa.head_pred_label,
  fa.head_pred_prob,
  fa.head_unknown_threshold,
  fa.head_is_another,
  fa.num_windows,
  fa.agg_mode
FROM file_aggregates fa;

COMMIT;
