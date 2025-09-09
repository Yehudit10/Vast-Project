CREATE TABLE IF NOT EXISTS images (
  image_id     BIGSERIAL PRIMARY KEY,
  fruit_type   VARCHAR(50) NOT NULL,
  captured_at  TIMESTAMP NOT NULL,
  source_path  VARCHAR(512) NOT NULL
);

CREATE TABLE IF NOT EXISTS detections (
  detection_id  BIGSERIAL PRIMARY KEY,
  image_id      BIGINT NOT NULL REFERENCES images(image_id),
  mean_h        REAL, mean_s REAL, mean_v REAL,
  laplacian_var REAL,
  brown_ratio   REAL,
  ripeness      VARCHAR(20) NOT NULL,   -- Unripe/Ripe/Overripe
  quality_flags INTEGER NOT NULL,
  created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weekly_rollups (
  fruit_type    VARCHAR(50) NOT NULL,
  iso_year      INT NOT NULL,
  iso_week      INT NOT NULL,
  cnt_total     INT NOT NULL,
  cnt_unripe    INT NOT NULL,
  cnt_ripe      INT NOT NULL,
  cnt_overripe  INT NOT NULL,
  pct_flagged   REAL NOT NULL,
  mean_brown    REAL,
  PRIMARY KEY (fruit_type, iso_year, iso_week)
);
