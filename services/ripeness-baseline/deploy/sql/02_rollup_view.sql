CREATE OR REPLACE VIEW v_weekly_ripeness AS
SELECT
  fruit_type,
  iso_year,
  iso_week,
  cnt_total,
  cnt_unripe,
  cnt_ripe,
  cnt_overripe,
  ROUND( (100.0 * cnt_ripe     / NULLIF(cnt_total,0))::numeric, 1 ) AS pct_ripe,
  ROUND( (100.0 * cnt_unripe   / NULLIF(cnt_total,0))::numeric, 1 ) AS pct_unripe,
  ROUND( (100.0 * cnt_overripe / NULLIF(cnt_total,0))::numeric, 1 ) AS pct_overripe,
  ROUND( (100.0 * pct_flagged)::numeric, 1 )                         AS pct_flagged,
  mean_brown
FROM weekly_rollups;
