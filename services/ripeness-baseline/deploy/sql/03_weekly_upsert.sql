WITH base AS (
  SELECT
    i.fruit_type,
    EXTRACT(ISOYEAR FROM i.captured_at)::INT as iso_year,
    EXTRACT(ISOWEEK FROM i.captured_at)::INT as iso_week,
    COUNT(*) AS cnt_total,
    SUM((d.ripeness='Unripe')::INT)    AS cnt_unripe,
    SUM((d.ripeness='Ripe')::INT)      AS cnt_ripe,
    SUM((d.ripeness='Overripe')::INT)  AS cnt_overripe,
    AVG((d.quality_flags>0)::INT)::REAL AS pct_flagged,
    AVG(d.brown_ratio)::REAL           AS mean_brown
  FROM images i
  JOIN detections d USING(image_id)
  WHERE i.captured_at >= NOW() - INTERVAL '21 days'
  GROUP BY 1,2,3
)
INSERT INTO weekly_rollups
  (fruit_type, iso_year, iso_week, cnt_total, cnt_unripe, cnt_ripe, cnt_overripe, pct_flagged, mean_brown)
SELECT fruit_type, iso_year, iso_week, cnt_total, cnt_unripe, cnt_ripe, cnt_overripe, pct_flagged, mean_brown
FROM base
ON CONFLICT (fruit_type, iso_year, iso_week) DO UPDATE
SET cnt_total   = EXCLUDED.cnt_total,
    cnt_unripe  = EXCLUDED.cnt_unripe,
    cnt_ripe    = EXCLUDED.cnt_ripe,
    cnt_overripe= EXCLUDED.cnt_overripe,
    pct_flagged = EXCLUDED.pct_flagged,
    mean_brown  = EXCLUDED.mean_brown;
