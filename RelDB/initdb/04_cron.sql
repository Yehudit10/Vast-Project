-- 04_cron.sql
-- תזמון משימות אוטומטיות עם pg_cron
-- רץ אחרי 03_partitions.sql (כך שכל הפונקציות קיימות)

CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 1) כל יום ראשון 03:00 – יצירת מחיצות לשבוע הבא
SELECT cron.schedule(
  'partitions-next-week',
  '0 3 * * 0',
  $$SELECT admin.ensure_next_week_partitions();$$
);

-- 2) כל 1 לחודש 03:10 – ריטנשן לשנה אחרונה
SELECT cron.schedule(
  'partitions-monthly-retention',
  '10 3 1 * *',
  $$SELECT admin.apply_yearly_retention();$$
);

-- 3) כל 10 דקות – רה-הומינג מהרירות (DEFAULT) למחיצות הנכונות
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
