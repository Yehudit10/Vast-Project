# rel_db.py
from __future__ import annotations
import os
import datetime as dt
from contextlib import contextmanager
from typing import Optional, List, Dict, Tuple
from functools import lru_cache

import psycopg2
from psycopg2.extras import RealDictCursor


# ---- ENV (Docker Compose defaults) ----
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_USER = os.getenv("DB_USER", "missions_user")
DB_PASS = os.getenv("DB_PASS", "pg123")
DB_NAME = os.getenv("DB_NAME", "missions_db")


@contextmanager
def _pg_conn():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, dbname=DB_NAME
    )
    try:
        yield conn
    finally:
        conn.close()


def _query(sql: str, params: tuple = ()) -> List[Dict]:
    try:
        with _pg_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        print(f"[RelDB][QUERY FAIL] {e}\n | SQL={sql!r} | params={params!r}")
        return []


# ---------- Dynamic schema ----------
@lru_cache(maxsize=1)
def _anomalies_cols() -> set[str]:
    rows = _query(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='anomalies'"
    )
    return {r["column_name"] for r in rows} if rows else set()

def _has_col(name: str) -> bool:
    return name in _anomalies_cols()

def _img_expr() -> str:
    """
    Adaptive image column:
      image_id (if exists) -> else tile_id -> else details->>'image_id'
    """
    if _has_col("image_id"):
        return "image_id"
    if _has_col("tile_id"):
        return "tile_id"
    return "(details->>'image_id')"

def _bbox_expr() -> str:
    """Adaptive bbox column: bbox or JSON."""
    if _has_col("bbox"):
        return "bbox"
    return "(details->'bbox')"

def _select_projection() -> str:
    """
    Returns SELECT column list with aliases to always include:
      anomaly_id, mission_id, device_id, ts, anomaly_type_id, severity,
      bbox, area, label, image_id, confidence, geom, details
    Even if some do not physically exist (extracted from JSON).
    """
    cols = [
        "anomaly_id",
        "mission_id",
        "device_id",
        "ts",
        "anomaly_type_id",
        "severity",
        f"{_bbox_expr()} AS bbox",
        # Derived from JSON (even if they exist physically, it’s fine; but we avoid name conflicts)
        "(details->>'area')::float AS area",
        "(details->>'label') AS label",
        f"{_img_expr()} AS image_id",
        "(details->>'confidence')::float AS confidence",
        "geom",
        "details",
    ]
    # If a physical column with the same name exists, prefer it (remove alias to avoid collision)
    if _has_col("area"):
        cols[cols.index("(details->>'area')::float AS area")] = "area"
    if _has_col("label"):
        cols[cols.index("(details->>'label') AS label")] = "label"
    if _has_col("confidence"):
        cols[cols.index("(details->>'confidence')::float AS confidence")] = "confidence"
    return ", ".join(cols)


class RelDB:
    """
    Thin data-access layer for the anomalies table.
    Works even when image_id/bbox are missing by using details(JSONB).
    """

    # ---------- Utilities ----------
    @staticmethod
    def _split_object_key(object_key: str) -> Tuple[str, str]:
        if not isinstance(object_key, str):
            return "", ""
        name = object_key.replace("\\", "/").split("/")[-1]
        if "." in name:
            base = ".".join(name.split(".")[:-1])
            ext = name.split(".")[-1]
            return base, ext
        return name, ""

    @staticmethod
    def _image_name_from_object_key(object_key: str) -> str:
        base, _ = RelDB._split_object_key(object_key)
        return base.strip()

    # ---------- Latest N ----------
    def get_latest_anomalies(self, limit: int = 20) -> List[Dict]:
        limit = max(1, min(int(limit or 20), 1000))
        cols = _select_projection()
        q_ts = f"SELECT {cols} FROM public.anomalies ORDER BY ts DESC LIMIT %s"
        rows = _query(q_ts, (limit,))
        if rows:
            return rows
        q_id = f"SELECT {cols} FROM public.anomalies ORDER BY anomaly_id DESC LIMIT %s"
        return _query(q_id, (limit,))

    # ---------- By image ----------
    def get_anomalies_by_image(self, image_name: str, limit: int = 50) -> List[Dict]:
        if not image_name:
            return []
        limit = max(1, min(int(limit or 50), 1000))
        cols = _select_projection()
        img_col = _img_expr()
        q_ts = f"""
            SELECT {cols}
            FROM public.anomalies
            WHERE {img_col} = %s
            ORDER BY ts DESC
            LIMIT %s
        """
        rows = _query(q_ts, (image_name, limit))
        if rows:
            return rows
        q_id = f"""
            SELECT {cols}
            FROM public.anomalies
            WHERE {img_col} = %s
            ORDER BY anomaly_id DESC
            LIMIT %s
        """
        return _query(q_id, (image_name, limit))

    def get_last_anomaly_by_image(self, image_name: str) -> Optional[Dict]:
        rows = self.get_anomalies_by_image(image_name, limit=1)
        return rows[0] if rows else None

    # ---------- From object key ----------
    def get_anomalies_for_image_key(self, object_key: str, limit: int = 50) -> List[Dict]:
        image_name = self._image_name_from_object_key(object_key)
        if not image_name:
            return []
        return self.get_anomalies_by_image(image_name, limit=limit)

    # ---------- Latest image present in DB ----------
    def get_latest_image_key(self) -> Optional[str]:
        img_col = _img_expr()
        if img_col.startswith("(") and "details" in img_col:
            # Can still filter based on the expression
            pass
        q_ts = f"""
          SELECT {img_col} AS img
          FROM public.anomalies
          WHERE {img_col} IS NOT NULL AND {img_col} <> ''
          ORDER BY ts DESC
          LIMIT 50
        """
        rows = _query(q_ts)
        if not rows:
            q_id = f"""
              SELECT {img_col} AS img
              FROM public.anomalies
              WHERE {img_col} IS NOT NULL AND {img_col} <> ''
              ORDER BY anomaly_id DESC
              LIMIT 50
            """
            rows = _query(q_id)
        for r in rows or []:
            v = r.get("img")
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    # ---------- By day ----------
    def get_anomalies_by_day(self, date_iso: str, limit: int = 1000) -> List[Dict]:
        try:
            day = dt.date.fromisoformat(date_iso)
        except Exception:
            print(f"[RelDB][DAY WARN] invalid date {date_iso!r}")
            return []
        start = dt.datetime.combine(day, dt.time.min)
        end = start + dt.timedelta(days=1)
        cols = _select_projection()
        q = f"""
            SELECT {cols}
            FROM public.anomalies
            WHERE ts >= %s AND ts < %s
            ORDER BY ts DESC
            LIMIT %s
        """
        rows = _query(q, (start, end, limit))
        if rows:
            return rows
        return self.get_latest_anomalies(limit=limit)

    # ---------- PHI helpers ----------
    @staticmethod
    def _sev_norm(x) -> Optional[float]:
        try:
            s = float(x)
        except Exception:
            return None
        if s < 0:
            return None
        return s if s <= 1.0 else min(s, 10.0) / 10.0

    @staticmethod
    def _phi_from(sev_avg_norm: Optional[float]) -> Optional[float]:
        if sev_avg_norm is None:
            return None
        return max(0.0, min(100.0, 100.0 * (1.0 - max(0.0, min(1.0, sev_avg_norm)))))

    # --- PHI per image ---
    def get_phi_for_image(self, image_name: str) -> Dict[str, Optional[float | str]]:
        if not image_name:
            return {"phi": None, "severity_avg": None, "image_id": None}
        img_col = _img_expr()
        q = f"""
            SELECT
              AVG(
                CASE
                  WHEN severity <= 1.0 THEN severity
                  WHEN severity >  1.0 THEN LEAST(severity, 10.0)/10.0
                  ELSE NULL
                END
              ) AS sev_avg_norm,
              COUNT(*) AS n_rows
            FROM public.anomalies
            WHERE {img_col} = %s
        """
        rows = _query(q, (image_name,))
        sev_avg = rows[0].get("sev_avg_norm") if rows else None
        phi = self._phi_from(sev_avg)
        return {
            "phi": phi,
            "severity_avg": float(sev_avg) if sev_avg is not None else None,
            "image_id": image_name,
        }

    def get_phi_for_current_image(self) -> Dict[str, Optional[float | str]]:
        image_name = self.get_latest_image_key()
        if not image_name:
            return {"phi": None, "severity_avg": None, "image_id": None}
        return self.get_phi_for_image(image_name)

    # --- Weekly PHI (backward compatibility) ---
    def get_weekly_phi(self) -> Dict[str, Optional[float | str]]:
        today = dt.date.today()
        week_start = today - dt.timedelta(days=today.weekday())   # Monday
        prev_week_start = week_start - dt.timedelta(days=7)
        week_end = week_start + dt.timedelta(days=7)
        prev_week_end = week_start

        def _week_stats(a: dt.date, b: dt.date):
            q = """
                SELECT
                  AVG(
                    CASE
                      WHEN severity <= 1.0 THEN severity
                      WHEN severity >  1.0 THEN LEAST(severity, 10.0)/10.0
                      ELSE NULL
                    END
                  ) AS sev_avg_norm,
                  COUNT(*) AS n_rows
                FROM public.anomalies
                WHERE ts >= %s AND ts < %s
            """
            rows = _query(q, (
                dt.datetime.combine(a, dt.time.min),
                dt.datetime.combine(b, dt.time.min),
            ))
            return rows[0] if rows else {"sev_avg_norm": None, "n_rows": 0}

        cur = _week_stats(week_start, week_end)
        prev = _week_stats(prev_week_start, prev_week_end)

        sev_avg = cur.get("sev_avg_norm")
        phi = self._phi_from(sev_avg)

        n_rows = (cur.get("n_rows") or 0)
        density = (n_rows / 7.0) if n_rows else None

        prev_phi = self._phi_from(prev.get("sev_avg_norm"))
        trend = (phi - prev_phi) if (phi is not None and prev_phi is not None) else None

        return {
            "phi": phi,
            "severity_avg": float(sev_avg) if sev_avg is not None else None,
            "density": float(density) if density is not None else None,
            "coverage": None,
            "trend": float(trend) if trend is not None else None,
            "week_start": str(week_start),
        }
