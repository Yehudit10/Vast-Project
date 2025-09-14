-- initdb/002_audio_cls_schema.sql
-- Minimal schema for our use-case (file-level only; no per-window predictions)

CREATE SCHEMA IF NOT EXISTS audio_cls;

-- ======================
-- runs: metadata per run
-- ======================
CREATE TABLE IF NOT EXISTS audio_cls.runs (
  run_id        TEXT PRIMARY KEY,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ,
  model_name    TEXT,
  checkpoint    TEXT,
  head_path     TEXT,
  labels_csv    TEXT,
  window_sec    DOUBLE PRECISION NOT NULL,
  hop_sec       DOUBLE PRECISION NOT NULL,
  pad_last      BOOLEAN NOT NULL,
  agg           TEXT NOT NULL,
  topk          INTEGER NOT NULL,
  device        TEXT NOT NULL,
  code_version  TEXT,
  notes         TEXT
);

-- =======================
-- files: input file facts
-- =======================
CREATE TABLE IF NOT EXISTS audio_cls.files (
  file_id      BIGSERIAL PRIMARY KEY,
  path         TEXT UNIQUE NOT NULL,
  duration_s   DOUBLE PRECISION,
  sample_rate  INTEGER,
  size_bytes   BIGINT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_audio_cls_files_path ON audio_cls.files(path);

-- ======================================================
-- file_aggregates: final per-file outputs (no per-window)
-- ======================================================
CREATE TABLE IF NOT EXISTS audio_cls.file_aggregates (
  run_id            TEXT   NOT NULL,
  file_id           BIGINT NOT NULL,
  audioset_topk_json  JSONB,
  head_p_animal     DOUBLE PRECISION CHECK (head_p_animal  IS NULL OR (head_p_animal  BETWEEN 0 AND 1)),
  head_p_vehicle    DOUBLE PRECISION CHECK (head_p_vehicle IS NULL OR (head_p_vehicle BETWEEN 0 AND 1)),
  head_p_shotgun    DOUBLE PRECISION CHECK (head_p_shotgun IS NULL OR (head_p_shotgun BETWEEN 0 AND 1)),
  head_p_other      DOUBLE PRECISION CHECK (head_p_other   IS NULL OR (head_p_other   BETWEEN 0 AND 1)),
  num_windows       INTEGER,
  agg_mode          TEXT,
  PRIMARY KEY (run_id, file_id),
  FOREIGN KEY (run_id)  REFERENCES audio_cls.runs(run_id)    ON DELETE CASCADE,
  FOREIGN KEY (file_id) REFERENCES audio_cls.files(file_id)  ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_audio_cls_file_agg_run ON audio_cls.file_aggregates(run_id);
