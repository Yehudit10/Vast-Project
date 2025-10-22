from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional

import psycopg2
import psycopg2.extras
from psycopg2.extensions import connection as PGConnection
from psycopg2 import sql
import logging

LOGGER = logging.getLogger(__name__)
_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

def open_db(db_url: str, schema: str = "audio_cls") -> PGConnection:
    if not db_url:
        raise ValueError("db_url is required (e.g., postgresql://user:pass@host:port/db)")
    if not _SCHEMA_RE.match(schema):
        raise ValueError(f"invalid schema name: {schema}")

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(schema)))
        conn.commit()
        LOGGER.info("DB connected; schema=%s", schema)
    except Exception:
        conn.rollback()
        LOGGER.exception("failed to init schema/search_path")
        raise
    return conn

def upsert_run(conn: PGConnection, meta: Dict[str, Any]) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs
                (run_id, model_name, checkpoint, head_path, labels_csv,
                 window_sec, hop_sec, pad_last, agg, topk, device, code_version, notes)
                VALUES
                (%(run_id)s, %(model_name)s, %(checkpoint)s, %(head_path)s, %(labels_csv)s,
                 %(window_sec)s, %(hop_sec)s, %(pad_last)s, %(agg)s, %(topk)s, %(device)s, %(code_version)s, %(notes)s)
                ON CONFLICT (run_id) DO NOTHING
                """,
                meta,
            )
        conn.commit()
        LOGGER.debug("upsert_run: %s", meta.get("run_id"))
    except Exception:
        conn.rollback()
        LOGGER.exception("upsert_run failed")
        raise

def finish_run(conn: PGConnection, run_id: str) -> None:
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE runs SET finished_at = now() WHERE run_id = %s", (run_id,))
        conn.commit()
        LOGGER.info("finish_run: %s", run_id)
    except Exception:
        conn.rollback()
        LOGGER.exception("finish_run failed: %s", run_id)
        raise

def upsert_file(
    conn: PGConnection,
    path: str,
    duration_s: Optional[float],
    sample_rate: Optional[int],
    size_bytes: Optional[int] = None,
) -> int:
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO files(path, duration_s, sample_rate, size_bytes)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (path) DO UPDATE SET
                  duration_s = EXCLUDED.duration_s,
                  sample_rate = EXCLUDED.sample_rate,
                  size_bytes = EXCLUDED.size_bytes
                RETURNING file_id
                """,
                (path, duration_s, sample_rate, size_bytes),
            )
            file_id = cur.fetchone()[0]
        conn.commit()
        LOGGER.debug("upsert_file: %s -> %d", path, file_id)
        return int(file_id)
    except Exception:
        conn.rollback()
        LOGGER.exception("upsert_file failed: %s", path)
        raise

def _jsonify(v: Any) -> psycopg2.extras.Json:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except Exception:
            v = {"raw": v}
    return psycopg2.extras.Json(v)

def upsert_file_aggregate(conn: PGConnection, row: Dict[str, Any]) -> None:
    data = dict(row)
    if "head_probs_json" in data and data["head_probs_json"] is not None:
        data["head_probs_json"] = _jsonify(data.get("head_probs_json"))

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO file_aggregates
                  (run_id, file_id,
                   head_probs_json, head_pred_label, head_pred_prob, head_unknown_threshold, head_is_another,
                   num_windows, agg_mode, processing_ms)
                VALUES
                  (%(run_id)s, %(file_id)s,
                   %(head_probs_json)s, %(head_pred_label)s, %(head_pred_prob)s, %(head_unknown_threshold)s, %(head_is_another)s,
                   %(num_windows)s, %(agg_mode)s, %(processing_ms)s)
                ON CONFLICT (run_id, file_id) DO UPDATE SET
                  head_probs_json         = EXCLUDED.head_probs_json,
                  head_pred_label         = EXCLUDED.head_pred_label,
                  head_pred_prob          = EXCLUDED.head_pred_prob,
                  head_unknown_threshold  = EXCLUDED.head_unknown_threshold,
                  head_is_another         = EXCLUDED.head_is_another,
                  num_windows             = EXCLUDED.num_windows,
                  agg_mode                = EXCLUDED.agg_mode,
                  processing_ms           = EXCLUDED.processing_ms
                """,
                data,
            )
        conn.commit()
        LOGGER.debug("upsert_file_aggregate: run=%s file=%s", data.get("run_id"), data.get("file_id"))
    except Exception:
        conn.rollback()
        LOGGER.exception("upsert_file_aggregate failed")
        raise

