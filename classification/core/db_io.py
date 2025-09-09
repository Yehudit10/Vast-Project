# core/db_io.py
# Minimal SQLite I/O for saving runs, files, per-window predictions, and file-level aggregates.

from __future__ import annotations

import sqlite3
from typing import Iterable, Dict, Any


def open_db(db_path: str) -> sqlite3.Connection:
    """Open (and create if needed) a SQLite database file."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create schema if not exists (4-table architecture)."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
          run_id        TEXT PRIMARY KEY,
          started_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
          finished_at   TIMESTAMP,
          model_name    TEXT,
          checkpoint    TEXT,
          head_path     TEXT,
          labels_csv    TEXT,
          window_sec    REAL NOT NULL,
          hop_sec       REAL NOT NULL,
          pad_last      INTEGER NOT NULL,
          agg           TEXT NOT NULL,
          topk          INTEGER NOT NULL,
          device        TEXT NOT NULL,
          code_version  TEXT,
          notes         TEXT
        );

        CREATE TABLE IF NOT EXISTS files (
          file_id        INTEGER PRIMARY KEY AUTOINCREMENT,
          path           TEXT UNIQUE NOT NULL,
          duration_s     REAL,
          sample_rate    INTEGER,
          size_bytes     INTEGER,
          content_sha256 TEXT
        );
        CREATE INDEX IF NOT EXISTS ix_files_path ON files(path);
        CREATE INDEX IF NOT EXISTS ix_files_sha  ON files(content_sha256);

        CREATE TABLE IF NOT EXISTS predictions (
          run_id       TEXT NOT NULL,
          file_id      INTEGER NOT NULL,
          segment_idx  INTEGER NOT NULL,
          t_start      REAL NOT NULL,
          t_end        REAL NOT NULL,
          audioset_topk_json  TEXT,
          p_animal     REAL,
          p_vehicle    REAL,
          p_shotgun    REAL,
          p_other      REAL,
          PRIMARY KEY (run_id, file_id, segment_idx),
          FOREIGN KEY (run_id)  REFERENCES runs(run_id),
          FOREIGN KEY (file_id) REFERENCES files(file_id)
        );
        CREATE INDEX IF NOT EXISTS ix_predictions_run   ON predictions(run_id);
        CREATE INDEX IF NOT EXISTS ix_predictions_file  ON predictions(file_id);
        CREATE INDEX IF NOT EXISTS ix_predictions_tspan ON predictions(file_id, t_start, t_end);

        CREATE TABLE IF NOT EXISTS file_aggregates (
          run_id     TEXT NOT NULL,
          file_id    INTEGER NOT NULL,
          audioset_topk_json  TEXT,
          head_p_animal   REAL,
          head_p_vehicle  REAL,
          head_p_shotgun  REAL,
          head_p_other    REAL,
          num_windows     INTEGER,
          agg_mode        TEXT,
          PRIMARY KEY (run_id, file_id),
          FOREIGN KEY (run_id) REFERENCES runs(run_id),
          FOREIGN KEY (file_id) REFERENCES files(file_id)
        );
        CREATE INDEX IF NOT EXISTS ix_file_agg_run ON file_aggregates(run_id);
        """
    )
    conn.commit()


def upsert_run(conn: sqlite3.Connection, meta: Dict[str, Any]) -> None:
    """Insert a run row. 'run_id' must be in meta."""
    conn.execute(
        """
        INSERT INTO runs
        (run_id, model_name, checkpoint, head_path, labels_csv, window_sec, hop_sec, pad_last, agg, topk, device, code_version, notes)
        VALUES (:run_id, :model_name, :checkpoint, :head_path, :labels_csv, :window_sec, :hop_sec, :pad_last, :agg, :topk, :device, :code_version, :notes)
        """,
        meta,
    )
    conn.commit()


def finish_run(conn: sqlite3.Connection, run_id: str) -> None:
    conn.execute("UPDATE runs SET finished_at=CURRENT_TIMESTAMP WHERE run_id=?", (run_id,))
    conn.commit()


def upsert_file(conn: sqlite3.Connection, path: str, duration_s: float | None, sample_rate: int | None,
                size_bytes: int | None = None, content_sha256: str | None = None) -> int:
    """Insert or update a file row and return file_id."""
    conn.execute(
        """
        INSERT INTO files(path, duration_s, sample_rate, size_bytes, content_sha256)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
          duration_s=excluded.duration_s,
          sample_rate=excluded.sample_rate,
          size_bytes=excluded.size_bytes,
          content_sha256=excluded.content_sha256
        """,
        (path, duration_s, sample_rate, size_bytes, content_sha256),
    )
    cur = conn.execute("SELECT file_id FROM files WHERE path=?", (path,))
    row = cur.fetchone()
    return int(row[0])


def insert_predictions_batch(conn: sqlite3.Connection, rows: Iterable[Dict[str, Any]]) -> None:
    """Batch insert per-window predictions."""
    conn.executemany(
        """
        INSERT OR REPLACE INTO predictions
        (run_id, file_id, segment_idx, t_start, t_end, audioset_topk_json, p_animal, p_vehicle, p_shotgun, p_other)
        VALUES (:run_id, :file_id, :segment_idx, :t_start, :t_end, :audioset_topk_json, :p_animal, :p_vehicle, :p_shotgun, :p_other)
        """,
        rows,
    )
    conn.commit()


def upsert_file_aggregate(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    """Upsert a single file-level aggregate row."""
    conn.execute(
        """
        INSERT OR REPLACE INTO file_aggregates
        (run_id, file_id, audioset_topk_json, head_p_animal, head_p_vehicle, head_p_shotgun, head_p_other, num_windows, agg_mode)
        VALUES (:run_id, :file_id, :audioset_topk_json, :head_p_animal, :head_p_vehicle, :head_p_shotgun, :head_p_other, :num_windows, :agg_mode)
        """,
        row,
    )
    conn.commit()
