-- 04_cron.sql
-- Scheduling automatic tasks with pg_cron
-- Runs after 03_partitions.sql (so that all functions already exist)
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 1) Every Sunday at 03:00 – create partitions for the coming week
SELECT cron.schedule(
  'partitions-next-week',
  '0 3 * * 0',
  $$SELECT admin.ensure_next_week_partitions();$$
);

-- 2) On the 1st of every month at 03:10 – retention for the last year
SELECT cron.schedule(
  'partitions-monthly-retention',
  '10 3 1 * *',
  $$SELECT admin.apply_yearly_retention();$$
);

-- 3) Every 10 minutes — re-homing from the default partition (DEFAULT) to the correct partitions
SELECT cron.schedule(
  'rehoming-telemetry-default',
  '*/10 * * * *',
  $$SELECT admin.rehome_telemetry_default();$$
);

SELECT cron.schedule(
  'rehoming-event-logs-default',
  '*/10 * * * *',
  $$SELECT admin.rehome_event_logs_default();$$
);
