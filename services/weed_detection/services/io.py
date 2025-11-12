from __future__ import annotations

import json
import logging
from typing import Tuple, Iterable, Dict, Any, List

import pandas as pd
from sqlalchemy import create_engine, text

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------
# Postgres sources: anomalies / anomaly_types / regions
# ---------------------------------------------------------------------

_BASE_SQLS: Dict[str, str] = {
    "device": """
        SELECT a.ts AS "timestamp",
               a.device_id AS entity_id,
               at.code AS disease_type,
               COALESCE(a.severity::double precision, 0.0) AS severity,
               0.0 AS affected_area
        FROM public.anomalies a
        JOIN public.anomaly_types at ON at.anomaly_type_id = a.anomaly_type_id
        WHERE a.ts IS NOT NULL
          {AND_CODE_FILTER}
          {AND_TIME_RANGE}
    """,
    "mission": """
        SELECT a.ts AS "timestamp",
               a.mission_id::text AS entity_id,
               at.code AS disease_type,
               COALESCE(a.severity::double precision, 0.0) AS severity,
               0.0 AS affected_area
        FROM public.anomalies a
        JOIN public.anomaly_types at ON at.anomaly_type_id = a.anomaly_type_id
        WHERE a.ts IS NOT NULL
          {AND_CODE_FILTER}
          {AND_TIME_RANGE}
    """,
    "region": """
        SELECT a.ts AS "timestamp",
               r.id::text AS entity_id,
               at.code AS disease_type,
               COALESCE(a.severity::double precision, 0.0) AS severity,
               {AREA_EXPR} AS affected_area
        FROM public.anomalies a
        JOIN public.anomaly_types at ON at.anomaly_type_id = a.anomaly_type_id
        JOIN public.regions r ON ST_Contains(r.geom, a.geom)
        WHERE a.ts IS NOT NULL AND a.geom IS NOT NULL
          {AND_CODE_FILTER}
          {AND_TIME_RANGE}
    """,
}


def _build_sql(
    entity_dim: str,
    area_strategy: str,
    codes: List[str] | None,
    start: str | None,
    end: str | None,
) -> tuple[str, dict]:
    """
    Build parametrized SQL for reading anomalies with chosen entity dimension and area strategy.
    """
    sql = _BASE_SQLS[entity_dim]
    area_expr = "0.0"
    if entity_dim == "region" and area_strategy == "region_area":
        area_expr = "ST_Area(r.geom::geography)::double precision"

    and_code = ""
    params: Dict[str, Any] = {}
    if codes:
        and_code = "AND at.code = ANY(:codes)"
        params["codes"] = codes

    and_time = ""
    if start:
        and_time += " AND a.ts >= :start_time"
        params["start_time"] = start
    if end:
        and_time += " AND a.ts < :end_time"
        params["end_time"] = end

    sql = (
        sql.replace("{AREA_EXPR}", area_expr)
           .replace("{AND_CODE_FILTER}", and_code)
           .replace("{AND_TIME_RANGE}", and_time)
    )
    return sql, params


# ---------------------------------------------------------------------
# Postgres input (canonical)
# ---------------------------------------------------------------------

def load_inputs_from_postgres(pg_url: str, tz: str, cfg: dict) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load inputs from Postgres (public.anomalies/anomaly_types/regions).
    Controlled by cfg['source_mapping'] (entity_dim, area_strategy, filters, codes).
    Returns:
      det: columns [timestamp, entity_id, disease_type, severity, affected_area]
      reg: columns [entity_id, entity_type]
    """
    edim = cfg["source_mapping"]["entity_dim"]
    area = cfg["source_mapping"].get("area_strategy", "none")
    codes = cfg["source_mapping"].get("anomaly_codes")
    filters = cfg["source_mapping"].get("filters") or {}
    start = filters.get("start_time")
    end = filters.get("end_time")

    sql, params = _build_sql(edim, area, codes, start, end)

    eng = create_engine(pg_url)
    with eng.begin() as conn:
        det = pd.read_sql(text(sql), conn, params=params)
        reg = det[["entity_id"]].drop_duplicates().assign(entity_type=edim)

    det["timestamp"] = pd.to_datetime(det["timestamp"], utc=True).dt.tz_convert(tz)

    required = {"timestamp", "entity_id", "disease_type", "severity", "affected_area"}
    if not required.issubset(det.columns):
        missing = required - set(det.columns)
        raise ValueError(f"det: missing {missing}")
    if not {"entity_id", "entity_type"}.issubset(reg.columns):
        raise ValueError("reg: missing cols")

    return det, reg


# ---------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------

def aggregate(det: pd.DataFrame, freq: str) -> pd.DataFrame:
    """
    Aggregate by entity_id + window and compute disease_count, avg_severity, affected_area.
    """
    df = det.copy()

    # Normalize tz: drop tz-info to use pandas period-based bucketing safely
    if pd.api.types.is_datetime64tz_dtype(df["timestamp"]):
        df["timestamp"] = df["timestamp"].dt.tz_convert("UTC").dt.tz_localize(None)

    df["window"] = df["timestamp"].dt.to_period(freq).dt.start_time
    grp = df.groupby(["entity_id", "window"], as_index=False).agg(
        disease_count=("disease_type", "count"),
        avg_severity=("severity", "mean"),
        affected_area=("affected_area", "sum"),
    )
    grp["window_end"] = grp["window"] + pd.tseries.frequencies.to_offset(freq)
    return grp


# ---------------------------------------------------------------------
# Alerts: Postgres backend
# ---------------------------------------------------------------------


def fetch_open_alerts_pg(pg_url: str) -> pd.DataFrame:
    eng = create_engine(pg_url)
    sql = """
      SELECT id, entity_id, rule, window_start, window_end, score,
             first_seen, last_seen, status, meta_json
      FROM public.alerts
      WHERE status IN ('OPEN','ACK')
    """
    with eng.begin() as conn:
        df = pd.read_sql(text(sql), conn)
    if not df.empty:
        for c in ("first_seen", "last_seen", "window_start", "window_end"):
            # make tz-aware UTC then drop tz -> naive UTC
            s = pd.to_datetime(df[c], utc=True)
            df[c] = s.dt.tz_convert("UTC").dt.tz_localize(None)

    return df


def upsert_alerts_pg(pg_url: str, alerts: Iterable[Dict[str, Any]]) -> None:
    rows = list(alerts)
    if not rows:
        return
    eng = create_engine(pg_url)
    sql = """
      INSERT INTO public.alerts
      (entity_id, rule, window_start, window_end, score,
       first_seen, last_seen, status, meta_json)
      VALUES
      (:entity_id, :rule, :window_start, :window_end, :score,
       :first_seen, :last_seen, :status, CAST(:meta_json AS jsonb))
    """
    payload = [{
        "entity_id": a["entity_id"],
        "rule": a["rule"],
        "window_start": a["window_start"],
        "window_end": a["window_end"],
        "score": float(a["score"]),
        "first_seen": a["first_seen"],
        "last_seen": a["last_seen"],
        "status": a["status"],
        "meta_json": json.dumps(a["meta"], ensure_ascii=False),
    } for a in rows]

    with eng.begin() as conn:
        conn.execute(text(sql), payload)
    LOGGER.info("Inserted %d alerts into Postgres.", len(rows))
