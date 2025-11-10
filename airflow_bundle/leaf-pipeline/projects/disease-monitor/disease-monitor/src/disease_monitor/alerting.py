from __future__ import annotations
import logging
from datetime import datetime
from typing import Dict, Any, List, Tuple
import pandas as pd

LOGGER = logging.getLogger(__name__)

def _merge_reasons(s: pd.Series) -> list[str]:
    items = []
    for x in s:
        if isinstance(x, (list, tuple, set)):
            items.extend(list(x))
        else:
            items.append(str(x))
    return sorted(set(items))

def enforce_policies(candidates: pd.DataFrame, open_alerts_df: pd.DataFrame,
                     cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Deduplicate per (entity, rule) with cooldown; update OPEN alerts if still anomalous;
    create RESOLVED entries after consecutive non-anomalous windows (handled by absence).
    Rate limiting applied.
    """
    if candidates.empty:
        return []

    candidates = candidates.copy()
    candidates["window_start"] = pd.to_datetime(candidates["window"])
    candidates["window_end"] = pd.to_datetime(candidates["window_end"])
    candidates["first_seen"] = candidates["window_start"]
    candidates["last_seen"] = candidates["window_end"]
    candidates["status"] = "OPEN"

    # Dedup cooldown: skip if there is OPEN/ACK within last N windows for same (entity, rule)
    cooldown = cfg["alerting"]["dedup_cooldown_windows"]
    frequency = cfg["windows"]["frequency"]

    alerts_out: List[Dict[str, Any]] = []
    rate_limit = cfg["alerting"]["rate_limit_per_run"]
    emitted = 0

    # Grouping by window if requested
    if cfg["alerting"]["group_by_window"]:
        group_keys = ["entity_id", "rule", "window_start", "window_end"]
    else:
        group_keys = ["entity_id", "rule"]

    g = candidates.groupby(group_keys, as_index=False).agg({
    "score": "max",
    "disease_count": "max",
    "avg_severity": "max",
    "affected_area": "max",
    "reason": _merge_reasons
})

    for _, row in g.iterrows():
        if emitted >= rate_limit:
            LOGGER.warning("Rate limit reached (%d).", rate_limit)
            break
        entity, rule = row["entity_id"], row["rule"]
        ws, we = row["window_start"], row["window_end"]
        # Check cooldown against open alerts
        if not open_alerts_df.empty:
            same = open_alerts_df[(open_alerts_df["entity_id"] == entity) &
                                  (open_alerts_df["rule"] == rule)]
            # In cooldown if last_seen within last cooldown windows
            recent = same[same["last_seen"] >= (ws - _windows_to_offset(frequency, cooldown))]
            if not recent.empty:
                LOGGER.info("Cooldown skip for %s/%s at %s.", entity, rule, ws)
                continue

        meta = {
            "reasons": row["reason"],
            "disease_count": int(row["disease_count"]),
            "avg_severity": float(row["avg_severity"]),
            "affected_area": float(row["affected_area"]),
        }
        alerts_out.append({
            "entity_id": entity,
            "rule": rule,
            "window_start": ws.to_pydatetime(),
            "window_end": we.to_pydatetime(),
            "score": float(row["score"]),
            "first_seen": ws.to_pydatetime(),
            "last_seen": we.to_pydatetime(),
            "status": "OPEN",
            "meta": meta
        })
        emitted += 1

    return alerts_out

def _windows_to_offset(freq: str, n: int) -> pd.Timedelta:
    if n <= 0:
        return pd.Timedelta(0)
    if freq.upper().startswith("W"):
        return pd.to_timedelta(7 * n, unit="D")
    return pd.to_timedelta(n, unit="D")
