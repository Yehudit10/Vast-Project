from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Iterable, List, Optional
from sqlalchemy import text

from agri_baseline.src.pipeline.db import get_engine, INSERT_FINDING, INSERT_QA


@dataclass
class Finding:
    """Single validation finding."""
    scope: str           # e.g., "image"
    image_id: str        # logical id per image
    rule: str            # rule code/name
    severity: str        # DEBUG/INFO/WARN/ERROR
    message: str         # human-readable message
    details: Optional[dict] = None


class Validator:
    """
    Collects validation findings and writes batch summaries.
    """
    def image_findings(self, findings: Iterable[Finding]) -> None:
        """Write image-level findings into event_logs table."""
        with get_engine().begin() as conn:
            for f in findings:
                details_dict = {
                    "scope": f.scope,
                    "rule": f.rule,
                    "image_id": f.image_id,
                    **(f.details or {}),
                }
                conn.execute(
                    INSERT_FINDING,
                    {
                        "level": f.severity.upper(),
                        "message": f.message,
                        # Passes as a JSON string because SQL does CAST(... AS jsonb)                        "details": json.dumps(details_dict),
                    },
                )


    def batch_summary(self) -> None:
        """
        Aggregate anomalies → tile_stats by image_id (from anomalies.details->>'image_id').
        For each (mission_id, image_id):
        - anomaly_score = count of anomalies
        - geom = envelope of a small expanded collect of points (Polygon, 4326)
        Idempotent via ON CONFLICT (mission_id, tile_id).
        """
        sql = text(
            """
            WITH per_image AS (
            SELECT
                a.mission_id,
                a.details->>'image_id' AS tile_id,
                COUNT(*)::real AS anomaly_score,
                -- produce Polygon in 4326 directly (no WKT roundtrip)
                ST_Envelope(
                ST_Expand(
                    ST_Collect(a.geom),
                    0.0005 -- ~50m at equator; tweak if needed
                )
                )::geometry(Polygon, 4326) AS poly
            FROM anomalies a
            WHERE a.geom IS NOT NULL
                AND a.details ? 'image_id'
            GROUP BY a.mission_id, tile_id
            )
            INSERT INTO tile_stats (mission_id, tile_id, anomaly_score, geom)
            SELECT mission_id, tile_id, anomaly_score, poly
            FROM per_image
            ON CONFLICT (mission_id, tile_id) DO UPDATE
            SET anomaly_score = EXCLUDED.anomaly_score,
                geom = EXCLUDED.geom;
            """
        )

        with get_engine().begin() as conn:
            conn.execute(sql)

        # optional: record a QA info log (pass JSON as string)
        with get_engine().begin() as conn:
            conn.execute(
                INSERT_QA,
                {
                    "details": json.dumps({
                        "source": "batch_summary",
                        "note": "tile_stats updated from anomalies by image_id",
                    })
                },
            )
