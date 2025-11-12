CREATE TABLE IF NOT EXISTS soil_moisture_events (
  id SERIAL PRIMARY KEY,
  device_id TEXT NOT NULL,
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
  device_id TEXT PRIMARY KEY,
  next_run_at TIMESTAMPTZ NOT NULL,
  duration_min INT NOT NULL,
  updated_by TEXT NOT NULL,
  update_reason TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS irrigation_schedule_audit (
  id SERIAL PRIMARY KEY,
  device_id TEXT NOT NULL,
  prev_next_run_at TIMESTAMPTZ,
  prev_duration_min INT,
  next_run_at TIMESTAMPTZ NOT NULL,
  duration_min INT NOT NULL,
  updated_by TEXT NOT NULL,
  update_reason TEXT NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE irrigation_policies (
    device_id TEXT NOT NULL,
    prev_state TEXT,
    dry_ratio_high REAL,
    dry_ratio_low REAL,
    min_patches INT,
    duration_min INT,
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (device_id),
    CONSTRAINT fk_device
        FOREIGN KEY (device_id) REFERENCES devices(device_id)
        ON DELETE CASCADE
);
