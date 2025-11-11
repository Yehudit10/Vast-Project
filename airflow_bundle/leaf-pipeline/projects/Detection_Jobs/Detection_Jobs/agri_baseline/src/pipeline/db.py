from __future__ import annotations

from sqlalchemy import create_engine, text, bindparam  
from sqlalchemy.engine import Engine

from . import config

_engine: Engine | None = None

def get_engine() -> Engine:
    """Return a singleton SQLAlchemy engine for the configured DB."""
    global _engine
    if _engine is None:
        _engine = create_engine(
            config.DB_URL,
            pool_pre_ping=True,                 # keep-alive for flaky networks/tests
            future=True,
            connect_args={"connect_timeout": 5} # fail fast on bad host/port
        )
    return _engine

# === Inserts mapped to RelDB schema ===

# detections → anomalies
INSERT_DET = text(
    """
    INSERT INTO anomalies(mission_id, device_id, ts, anomaly_type_id, severity, details, geom)
    VALUES (:mission_id, :device_id, :ts, :anomaly_type_id, :severity, CAST(:details AS jsonb),
            ST_GeomFromText(:wkt_geom, 4326));
    """
)

# counts → tile_stats
INSERT_COUNT = text(
    """
    INSERT INTO tile_stats(mission_id, tile_id, anomaly_score, geom)
    VALUES (:mission_id, :tile_id, :anomaly_score, ST_GeomFromText(:wkt_geom, 4326))
    ON CONFLICT (mission_id, tile_id) DO UPDATE
      SET anomaly_score = excluded.anomaly_score;
    """
)

# validator findings → event_logs
INSERT_FINDING = (
    text(
        """
        INSERT INTO event_logs(ts, level, source, message, details)
        VALUES (CURRENT_TIMESTAMP, :level, 'validator', :message, CAST(:details AS jsonb));
        """
    )
    # Defaults if the caller does not send the parameters
    .bindparams(
        bindparam("level", value="INFO"),
        bindparam("message", value=""),
        bindparam("details", value="{}"),
    )
)



# QA metrics → event_logs
INSERT_QA = text(
    """
    INSERT INTO event_logs(ts, level, source, message, details)
    VALUES (CURRENT_TIMESTAMP, 'INFO', 'qa', 'QA metrics recorded', CAST(:details AS jsonb));
    """
)