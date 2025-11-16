

from datetime import date
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta

# ─────────────────────────────────────────────
# Database Connection
# ─────────────────────────────────────────────
engine = create_engine(
    "postgresql+psycopg2://missions_user:pg123@postgres:5432/missions_db",
    echo=False
)

# ─────────────────────────────────────────────
# Load all regions & devices
# ─────────────────────────────────────────────
def load_all_regions() -> list[dict]:
    """Return all regions with ID, name, and geometry."""
    query = text("""
        SELECT id, name, ST_AsGeoJSON(geom) AS geom
        FROM regions
        ORDER BY id;
    """)
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(query).mappings().all()]


def load_all_devices() -> list[dict]:
    """Return all devices with ID, model, owner, and coordinates."""
    query = text("""
        SELECT device_id, model, owner, active,
               location_lat, location_lon
        FROM devices
        WHERE owner = 'security'
        ORDER BY device_id;
    """)
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(query).mappings().all()]

# ─────────────────────────────────────────────
# DEVICE ANALYTICS (supports multiple or all devices)
# ─────────────────────────────────────────────
def get_device_analytics(device_ids=None, start_date=None, end_date=None) -> dict:
    """
    Return aggregated alert analytics for one or more devices.
    If device_ids is None or empty, aggregates all devices.
    """
    if isinstance(device_ids, str):
        device_ids = [device_ids]

    # Default to full current year range if missing
    if not start_date:
        start_date = date.today().replace(day=1, month=1)
    if not end_date:
        end_date = date.today()

    # Convert to datetime range that includes the entire end day
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())


    with engine.connect() as conn:
        params = {"device_ids": device_ids or [],
          "start_date": start_dt,
          "end_date": end_dt}


        if device_ids:
            device_filter = "AND device_id = ANY(:device_ids)"
        else:
            device_filter = ""  # ← no filter means aggregate all devices
            params.pop("device_ids", None)


        # Alerts by Type
        q_by_type = text(f"""
            SELECT alert_type, COUNT(*) AS count
            FROM alerts
            WHERE started_at BETWEEN :start_date AND :end_date
              {device_filter}
            GROUP BY alert_type
            ORDER BY count DESC;
        """)
        by_type = {r["alert_type"] or "Unknown": r["count"]
                   for r in conn.execute(q_by_type, params).mappings().all()}

        # Alerts per Month
        q_month = text(f"""
            WITH months AS (
                SELECT TO_CHAR(gs, 'YYYY-MM') AS month
                FROM generate_series(
                    date_trunc('month', CAST(:start_date AS timestamp)),
                    date_trunc('month', CAST(:end_date AS timestamp)),
                    interval '1 month'
                ) AS gs
            ),
            alert_counts AS (
                SELECT TO_CHAR(started_at, 'YYYY-MM') AS month, COUNT(*) AS count
                FROM alerts
                WHERE started_at BETWEEN :start_date AND :end_date
                  {device_filter}
                GROUP BY TO_CHAR(started_at, 'YYYY-MM')
            )
            SELECT m.month, COALESCE(ac.count, 0) AS count
            FROM months m
            LEFT JOIN alert_counts ac ON ac.month = m.month
            ORDER BY m.month;
        """)
        per_month = {r["month"]: r["count"]
                     for r in conn.execute(q_month, params).mappings().all()}

        # Totals & averages
        q_total = text(f"""
            SELECT COUNT(*) AS total,
                   AVG(severity)::numeric(10,2) AS avg_severity,
                   AVG(confidence)::numeric(10,2) AS avg_confidence
            FROM alerts
            WHERE started_at BETWEEN :start_date AND :end_date
              {device_filter};
        """)
        total = conn.execute(q_total, params).mappings().first() or {}
        q_avg_duration = text(f"""
        SELECT alert_type,
            ROUND(AVG(EXTRACT(EPOCH FROM (ended_at - started_at)) / 60.0), 2) AS avg_minutes
        FROM alerts
        WHERE started_at BETWEEN :start_date AND :end_date
        {device_filter}
        AND ended_at IS NOT NULL
        GROUP BY alert_type
        ORDER BY avg_minutes DESC;
    """)

        avg_duration = {
            r["alert_type"] or "Unknown": float(r["avg_minutes"] or 0)
            for r in conn.execute(q_avg_duration, params).mappings().all()
        }

    
        return {
            "alerts_by_type": by_type,
            "alerts_per_month": per_month,
            "total_alerts": total.get("total", 0),
            "avg_severity": float(total.get("avg_severity") or 0),
            "avg_confidence": float(total.get("avg_confidence") or 0),
            "avg_duration_per_type": avg_duration,   # ← NEW
        }

# ─────────────────────────────────────────────
# REGION ANALYTICS (supports multiple or all regions)
# ─────────────────────────────────────────────
def get_region_analytics(region_ids=None, start_date=None, end_date=None) -> dict:
    """
    Aggregates analytics for one or more regions (using PostGIS ST_Intersects).
    If region_ids is None or empty, aggregates all regions.
    """
    if isinstance(region_ids, (str, int)):
        region_ids = [region_ids]

    # Default to full current year range if missing
    if not start_date:
        start_date = date.today().replace(day=1, month=1)
    if not end_date:
        end_date = date.today()

    # Convert to datetime range that includes the entire end day
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date + timedelta(days=1), datetime.min.time())


    with engine.connect() as conn:
        params = {
    "region_ids": region_ids or [],
    "start_date": start_dt,
    "end_date": end_dt,
}


        # Optional region filter
        if region_ids:
            region_filter = "AND r.id = ANY(:region_ids)"
        else:
            region_filter = ""  # no filter → aggregate all regions
            params.pop("region_ids", None)

        # Alerts by Type
        q_by_type = text(f"""
            SELECT a.alert_type, COUNT(*) AS count
            FROM alerts a
            JOIN devices d ON a.device_id = d.device_id
            JOIN regions r
              ON ST_Intersects(ST_Buffer(r.geom, 0.0002), ST_SetSRID(ST_MakePoint(d.location_lon, d.location_lat), 4326))
            WHERE a.started_at BETWEEN :start_date AND :end_date
              {region_filter}
            GROUP BY a.alert_type
            ORDER BY count DESC;
        """)
        print(q_by_type,region_filter)
        by_type = {r["alert_type"] or "Unknown": r["count"]
                   for r in conn.execute(q_by_type, params).mappings().all()}

        # Alerts per Month
        q_month = text(f"""
            WITH months AS (
                SELECT TO_CHAR(gs, 'YYYY-MM') AS month
                FROM generate_series(
                    date_trunc('month', CAST(:start_date AS timestamp)),
                    date_trunc('month', CAST(:end_date AS timestamp)),
                    interval '1 month'
                ) AS gs
            ),
            alert_counts AS (
                SELECT TO_CHAR(a.started_at, 'YYYY-MM') AS month, COUNT(*) AS count
                FROM alerts a
                JOIN devices d ON a.device_id = d.device_id
                JOIN regions r
                  ON ST_Intersects(ST_Buffer(r.geom, 0.0002), ST_SetSRID(ST_MakePoint(d.location_lon, d.location_lat), 4326))
                WHERE a.started_at BETWEEN :start_date AND :end_date
                  {region_filter}
                GROUP BY TO_CHAR(a.started_at, 'YYYY-MM')
            )
            SELECT m.month, COALESCE(ac.count, 0) AS count
            FROM months m
            LEFT JOIN alert_counts ac ON ac.month = m.month
            ORDER BY m.month;
        """)
        per_month = {r["month"]: r["count"]
                     for r in conn.execute(q_month, params).mappings().all()}

        # Totals & averages
        q_total = text(f"""
            SELECT COUNT(*) AS total,
                   AVG(a.severity)::numeric(10,2) AS avg_severity,
                   AVG(a.confidence)::numeric(10,2) AS avg_confidence
            FROM alerts a
            JOIN devices d ON a.device_id = d.device_id
            JOIN regions r
              ON ST_Intersects(ST_Buffer(r.geom, 0.0002), ST_SetSRID(ST_MakePoint(d.location_lon, d.location_lat), 4326))
            WHERE a.started_at BETWEEN :start_date AND :end_date
              {region_filter};
        """)
        total = conn.execute(q_total, params).mappings().first() or {}

        q_avg_duration = text(f"""
            SELECT a.alert_type,
                ROUND(AVG(EXTRACT(EPOCH FROM (a.ended_at - a.started_at)) / 60.0), 2) AS avg_minutes
            FROM alerts a
            JOIN devices d ON a.device_id = d.device_id
            JOIN regions r
            ON ST_Intersects(
                ST_Buffer(r.geom, 0.0002),
                ST_SetSRID(ST_MakePoint(d.location_lon, d.location_lat), 4326)
                )
            WHERE a.started_at BETWEEN :start_date AND :end_date
            {region_filter}
            AND a.ended_at IS NOT NULL
            GROUP BY a.alert_type
            ORDER BY avg_minutes DESC;
        """)
        avg_duration = {
            r["alert_type"] or "Unknown": float(r["avg_minutes"] or 0)
            for r in conn.execute(q_avg_duration, params).mappings().all()
        }

    
        return {
            "alerts_by_type": by_type,
            "alerts_per_month": per_month,
            "total_alerts": total.get("total", 0),
            "avg_severity": float(total.get("avg_severity") or 0),
            "avg_confidence": float(total.get("avg_confidence") or 0),
            "avg_duration_per_type": avg_duration,   # ← NEW
        }


# ─────────────────────────────────────────────
# NATURAL LANGUAGE QUERY SUPPORT
# ─────────────────────────────────────────────
from src.vast.views.security.analytics.sql_generator import generate_sql_from_prompt



def select_entities_from_prompt(prompt: str) -> dict:
    """
    Uses the AI SQL generator to convert free-text query → SQL,
    executes it, and returns matching entity IDs.

    Returns a dict:
    {
      "target": "region" | "device" | None,
      "ids": [list of IDs]
    }
    """
    sql, params = generate_sql_from_prompt(prompt)
    print(sql,params)
    if not sql:
        return {"target": None, "ids": []}

    with engine.connect() as conn:
        rows = [r[0] for r in conn.execute(text(sql), params)]

    
    sql_lower = sql.lower()
    if "area" in sql_lower or "region" in sql_lower:
        target = "region"
    elif "device_id" in sql_lower:
        target = "device"
    else:
        target = "region" if "from regions" in sql_lower else "device"
    
    import re

    if target == "region":
        # Normalize region names to lowercase without spaces/underscores for fuzzy match
        def normalize(name: str) -> str:
            return re.sub(r'[^a-z0-9]', '', name.lower())

        region_map = {normalize(r["name"]): r["id"] for r in load_all_regions()}

        mapped = []
        for r in rows:
            if isinstance(r, (int, float)):
                mapped.append(int(r))
            elif isinstance(r, str):
                key = normalize(r)
                if key in region_map:
                    mapped.append(region_map[key])
        rows = mapped


    return {"target": target, "ids": rows}


