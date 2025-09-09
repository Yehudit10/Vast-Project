# Ripeness Baseline (C24)

Baseline לקביעת בשלות פרי ע"פ **צבע+מרקם** בלבד (ללא ML):
- סגמנטציה ב-HSV → חישוב פיצ’רים (mean H,S,V, Laplacian var, brown_ratio, mask_coverage)
- סיווג: Unripe / Ripe / Overripe
- Quality Flags: LOW_LIGHT, BLURRY, SMALL_MASK, NEAR_THRESHOLD, OUTLIER
- כתיבה ל-Postgres: `images`, `detections`
- Rollup שבועי לטבלה `weekly_rollups` (ISO week)

## Run local
1. צרי DB Postgres והגדירי `.env` (PGHOST/…).
2. שימי תמונות ב-`samples/`.
3. התקני תלויות: `pip install -r requirements.txt`
4. הרצה: `PYTHONPATH=src python src/main.py`
   - ייצור סכימה אם חסרה
   - יכניס detections
   - יריץ upsert ל-weekly_rollups

## Docker
