import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

TZ = "UTC"

def make_series(start: str, days: int, entity: str, base_count=1, bump_at=None, bump=5):
    rows = []
    start_dt = pd.to_datetime(start).tz_localize("UTC")
    for i in range(days):
        ts = start_dt + pd.Timedelta(days=i)
        count = base_count
        if bump_at is not None and i in bump_at:
            count = bump
        rows.append({"timestamp": ts, "entity_id": entity, "disease_type": "x",
                     "severity": 0.1 * count, "affected_area": 2.0 * count})
    return pd.DataFrame(rows)
