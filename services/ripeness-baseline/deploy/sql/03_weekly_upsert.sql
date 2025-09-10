WITH base AS (
  SELECT
    i.fruit_type,
    to_char(i.captured_at, 'IYYY')::INT AS iso_year,  -- ISO year
    to_char(i.captured_at, 'IW')::INT   AS iso_week,  -- ISO week number (01-53)
    COUNT(*) AS cnt_total,
    SUM((d.ripeness='Unripe')::INT)    AS cnt_unripe,
    SUM((d.ripeness='Ripe')::INT)      AS cnt_ripe,
    SUM((d.ripeness='Overripe')::INT)  AS cnt_overripe,
    AVG((d.quality_flags>0)::INT)::REAL AS pct_flagged,
    AVG(d.brown_ratio)::REAL           AS mean_brown
  FROM images i
  JOIN detections d USING(image_id)
  -- לא חייבים לסנן בזמן ריצה, אבל השארתי חלון 21 יום כדי לא לגרד היסטוריה עצומה בכל הרצה
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
