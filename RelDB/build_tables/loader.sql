-- Extended synthetic data loader for schema_extended_v2.sql

-- Insert devices
INSERT INTO devices (device_id, model, owner, active) VALUES
  ('dev-a','drone-x','TeamA',true),
  ('dev-b','drone-x','TeamA',true),
  ('dev-c','rover-y','TeamB',true),
  ('dev-d','rover-y','TeamB',true),
  ('dev-e','sensor-z','TeamC',true),
  ('dev-f','sensor-z','TeamC',true)
ON CONFLICT DO NOTHING;

-- Insert some regions
INSERT INTO regions (name, geom)
VALUES
  ('North Field', ST_GeomFromText('POLYGON((34.75 32.00,34.90 32.00,34.90 32.10,34.75 32.10,34.75 32.00))',4326)),
  ('South Field', ST_GeomFromText('POLYGON((34.90 31.95,35.05 31.95,35.05 32.05,34.90 32.05,34.90 31.95))',4326))
ON CONFLICT DO NOTHING;

-- Insert anomaly types
INSERT INTO anomaly_types (code, description)
VALUES
  ('ALT_LOW','Altitude too low'),
  ('ALT_HIGH','Altitude too high'),
  ('SENSOR_FAIL','Sensor failure'),
  ('COMM_LOSS','Communication lost')
ON CONFLICT DO NOTHING;

-- Insert 5 missions
WITH params AS (
  SELECT 34.75::double precision AS min_lon, 35.05 AS max_lon,
         31.95::double precision AS min_lat, 32.20 AS max_lat
)
INSERT INTO missions (start_time, end_time, area_geom)
SELECT
  now() - (i || ' hours')::interval,
  now() - ((i-1) || ' hours')::interval,
  ST_MakePolygon(ST_GeomFromText(
      format('LINESTRING(%1$s %3$s,%2$s %3$s,%2$s %4$s,%1$s %4$s,%1$s %3$s)',
             min_lon, max_lon, min_lat, max_lat), 4326))
FROM params, generate_series(5,1,-1) AS s(i);

-- Insert telemetry (~60k rows for demo; adjust up for perf test)
WITH params AS (
  SELECT 34.75::double precision AS min_lon, 35.05 AS max_lon,
         31.95::double precision AS min_lat, 32.20 AS max_lat
),
devices AS (
  SELECT device_id FROM devices
),
ins AS (
  INSERT INTO telemetry (mission_id, device_id, ts, geom, altitude)
  SELECT
    (SELECT mission_id FROM missions ORDER BY random() LIMIT 1),
    d.device_id,
    now() - ((g % 10000) || ' seconds')::interval,
    ST_SetSRID(ST_MakePoint(
      (p.min_lon + random()*(p.max_lon - p.min_lon)),
      (p.min_lat + random()*(p.max_lat - p.min_lat))
    ),4326),
    50 + (random()*150)::int
  FROM params p, devices d, generate_series(1,10000) g
  RETURNING 1
)
SELECT count(*) AS rows_inserted FROM ins;

-- Insert tile_stats (small demo set)
WITH params AS (
  SELECT 34.75::double precision AS min_lon, 35.05 AS max_lon,
         31.95::double precision AS min_lat, 32.20 AS max_lat
),
T AS (
  SELECT
    (SELECT mission_id FROM missions ORDER BY random() LIMIT 1) AS mission_id,
    'tile-' || gs AS tile_id,
    (random()*10)::real AS anomaly_score,
    ST_Buffer(
      ST_SetSRID(ST_MakePoint(
        (min_lon + random()*(max_lon - min_lon)),
        (min_lat + random()*(max_lat - min_lat))
      ),4326)::geography,50,'quad_segs=2'
    )::geometry(Polygon,4326) AS geom
  FROM params, generate_series(1,1000) AS gs
)
INSERT INTO tile_stats (mission_id, tile_id, anomaly_score, geom)
SELECT mission_id, tile_id, anomaly_score, geom FROM T;

-- Insert anomalies
INSERT INTO anomalies (mission_id, device_id, ts, anomaly_type_id, severity, details, geom)
SELECT
  (SELECT mission_id FROM missions ORDER BY random() LIMIT 1),
  (SELECT device_id FROM devices ORDER BY random() LIMIT 1),
  now() - ((g % 5000) || ' seconds')::interval,
  (SELECT anomaly_type_id FROM anomaly_types ORDER BY random() LIMIT 1),
  (random()*10)::real,
  jsonb_build_object('note','synthetic anomaly'),
  ST_SetSRID(ST_MakePoint(34.8+random()*0.2,31.95+random()*0.25),4326)
FROM generate_series(1,200) g;

-- Insert files metadata (synthetic)
INSERT INTO files (bucket, object_key, content_type, size_bytes, etag, mission_id, device_id, metadata)
SELECT
  'mission-data',
  'images/img_'||g||'.jpg',
  'image/jpeg',
  (100000+random()*200000)::bigint,
  md5(random()::text),
  (SELECT mission_id FROM missions ORDER BY random() LIMIT 1),
  (SELECT device_id FROM devices ORDER BY random() LIMIT 1),
  jsonb_build_object('note','synthetic file')
FROM generate_series(1,20) g;

-- Insert event logs (small demo set)
INSERT INTO event_logs (ts, level, source, message, details, trace_id, user_id)
SELECT
  now() - ((g % 1000) || ' seconds')::interval,
  (ARRAY['INFO','WARN','ERROR'])[1+floor(random()*3)::int],
  (ARRAY['ingestor','api','flink-job'])[1+floor(random()*3)::int],
  'Synthetic log message #'||g,
  jsonb_build_object('note','synthetic log'),
  md5(g::text),
  CASE WHEN random()<0.3 THEN (100+g) ELSE -1 END
FROM generate_series(1,100) g;
