-- partition_maintenance.sql
CREATE SCHEMA IF NOT EXISTS admin;

-- Helper: create [from,to)
CREATE OR REPLACE FUNCTION admin.create_range_partition(
  parent_table  text,
  part_name     text,
  from_ts       timestamptz,
  to_ts         timestamptz
) RETURNS void
LANGUAGE plpgsql AS $func$
BEGIN
  EXECUTE format(
    'CREATE TABLE IF NOT EXISTS %I PARTITION OF %s FOR VALUES FROM (%L) TO (%L)',
    part_name, parent_table, from_ts, to_ts
  );
END;
$func$;

-- Per-partition indexes (telemetry_new)
CREATE OR REPLACE FUNCTION admin.ensure_telemetry_partition_indexes(part_name text)
RETURNS void LANGUAGE plpgsql AS $func$
BEGIN
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I_ts_brin     ON %I USING BRIN (ts);',           part_name, part_name);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I_mission_ts  ON %I (mission_id, ts);',           part_name, part_name);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I_geom_gist   ON %I USING GIST (geom);',          part_name, part_name);
END;
$func$;

-- Per-partition indexes (event_logs)
CREATE OR REPLACE FUNCTION admin.ensure_event_logs_partition_indexes(part_name text)
RETURNS void LANGUAGE plpgsql AS $func$
BEGIN
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I_ts_brin   ON %I USING BRIN (ts);', part_name, part_name);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I_level     ON %I (level);',         part_name, part_name);
  EXECUTE format('CREATE INDEX IF NOT EXISTS %I_source    ON %I (source);',        part_name, part_name);
END;
$func$;

-- Daily partitions (telemetry_new)
CREATE OR REPLACE FUNCTION admin.make_daily_partitions_telemetry(
  start_day date,
  num_days integer
) RETURNS void
LANGUAGE plpgsql AS $func$
DECLARE
  i int; d_from timestamptz; d_to timestamptz; pname text;
BEGIN
  FOR i IN 0..num_days-1 LOOP
    d_from := (start_day + i)::timestamptz;
    d_to   := (start_day + i + 1)::timestamptz;
    pname  := 'telemetry_new_p' || to_char(d_from,'YYYYMMDD');
    PERFORM admin.create_range_partition('public.telemetry_new', pname, d_from, d_to);
    PERFORM admin.ensure_telemetry_partition_indexes(pname);
  END LOOP;
END;
$func$;

-- Weekly partitions (event_logs)
CREATE OR REPLACE FUNCTION admin.make_weekly_partitions_event_logs(
  week_start date,
  num_weeks integer
) RETURNS void
LANGUAGE plpgsql AS $func$
DECLARE
  i int; w_from timestamptz; w_to timestamptz; pname text; aligned date;
BEGIN
  aligned := date_trunc('week', week_start::timestamptz)::date;
  FOR i IN 0..num_weeks-1 LOOP
    w_from := (aligned + (i*7))::timestamptz;
    w_to   := (aligned + (i*7+7))::timestamptz;
    pname  := 'event_logs_p' || to_char(w_from,'IYYYIW');
    PERFORM admin.create_range_partition('public.event_logs', pname, w_from, w_to);
    PERFORM admin.ensure_event_logs_partition_indexes(pname);
  END LOOP;
END;
$func$;

-- Driver: next week
CREATE OR REPLACE FUNCTION admin.ensure_next_week_partitions() RETURNS void
LANGUAGE plpgsql AS $func$
DECLARE
  next_monday date := date_trunc('week', now())::date + 7;
BEGIN
  PERFORM admin.make_daily_partitions_telemetry(next_monday, 7);
  PERFORM admin.make_weekly_partitions_event_logs(next_monday, 1);
END;
$func$;

-- Retention: drop partitions whose UPPER bound < now()-keep
CREATE OR REPLACE FUNCTION admin.drop_old_partitions(
  parent_table regclass,
  keep_interval interval
) RETURNS int
LANGUAGE plpgsql AS $func$
DECLARE
  r record;
  to_ts timestamptz;
  dropped int := 0;
  bound_text text;
BEGIN
  FOR r IN
    SELECT c.oid,
           format('%s.%I', n.nspname, c.relname) AS partname,
           pg_get_expr(c.relpartbound, c.oid, true) AS bound
    FROM pg_inherits i
    JOIN pg_class   c ON c.oid = i.inhrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE i.inhparent = parent_table
  LOOP
    bound_text := r.bound;

    BEGIN
      -- Example bound text: FOR VALUES FROM ('2025-08-01 ...') TO ('2025-08-02 ...')
      SELECT substring(bound_text from 'TO \(''([^'']+)''\)')::timestamptz INTO to_ts;

      IF to_ts IS NOT NULL AND to_ts < (now() AT TIME ZONE 'UTC') - keep_interval THEN
        EXECUTE format('DROP TABLE IF EXISTS %s;', r.partname);
        dropped := dropped + 1;
      END IF;
    EXCEPTION WHEN others THEN
      CONTINUE; -- skip DEFAULT/unexpected
    END;
  END LOOP;

  RETURN dropped;
END;
$func$;

-- One-year retention wrapper
CREATE OR REPLACE FUNCTION admin.apply_yearly_retention()
RETURNS void LANGUAGE plpgsql AS $func$
BEGIN
  PERFORM admin.drop_old_partitions('public.telemetry_new', interval '1 year');
  PERFORM admin.drop_old_partitions('public.event_logs',   interval '1 year');
END;
$func$;

-- -- =========================
-- -- pg_cron scheduling (optional but recommended)
-- -- =========================
-- CREATE EXTENSION IF NOT EXISTS pg_cron;

-- -- Every Sunday 03:00 – create next week's partitions (+ next 7 days)
-- SELECT cron.schedule(
--   'partitions-next-week',
--   '0 3 * * 0',
--   $$SELECT admin.ensure_next_week_partitions();$$
-- );

-- -- 1st of every month 03:10 – retention (keep 1 year)
-- SELECT cron.schedule(
--   'partitions-monthly-retention',
--   '10 3 1 * *',
--   $$SELECT admin.apply_yearly_retention();$$
-- );
