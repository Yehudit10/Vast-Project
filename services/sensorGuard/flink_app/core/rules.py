from typing import Optional, Dict, Any
from datetime import timezone
from .types import Event, Alert, DeviceState

def _utc(dt):
    """Return datetime with UTC tzinfo."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

def out_of_range(event: Event, cfg: Dict[str, Any]) -> Optional[Alert]:
    """Check if sensor value is outside configured min/max."""
    if event.msg_type not in ["reading", "telemetry"] or event.value is None:
        return None
    rngs = (cfg or {}).get("ranges", {})
    lim = rngs.get(event.sensor_type, {})
    vmin, vmax = lim.get("min"), lim.get("max")
    print(f"[RULES] out_of_range: sensor_type={event.sensor_type}, value={event.value}, lim={lim}, vmin={vmin}, vmax={vmax}")
    if vmin is not None and event.value < vmin:
        return Alert(
            device_id=event.device_id, issue_type="out_of_range",
            start_ts=_utc(event.ts), end_ts=None, severity="warn",
            sensor_type=event.sensor_type, site_id=event.site_id,
            details={"value": event.value, "min": vmin, "max": vmax}
        )
    if vmax is not None and event.value > vmax:
        return Alert(
            device_id=event.device_id, issue_type="out_of_range",
            start_ts=_utc(event.ts), end_ts=None, severity="warn",
            sensor_type=event.sensor_type, site_id=event.site_id,
            details={"value": event.value, "min": vmin, "max": vmax}
        )
    return None

def corrupted(event: Event, cfg: Dict[str, Any]) -> Optional[Alert]:
    """Check if reading is invalid (null, non-numeric, bad quality)."""
    if event.msg_type not in ["reading", "telemetry"]:
        return None
    if event.value is None:
        return Alert(
            device_id=event.device_id, issue_type="corrupted",
            start_ts=_utc(event.ts), end_ts=None, severity="error",
            sensor_type=event.sensor_type, site_id=event.site_id,
            details={"reason": "null value"}
        )

    if not isinstance(event.value, (int, float)):
        return Alert(
            device_id=event.device_id, issue_type="corrupted",
            start_ts=_utc(event.ts), end_ts=None, severity="error",
            sensor_type=event.sensor_type, site_id=event.site_id,
            details={"reason": "non-numeric"}
        )
    
    if event.quality and event.quality != "ok":
        return Alert(
            device_id=event.device_id, issue_type="corrupted",
            start_ts=_utc(event.ts), end_ts=None, severity="error",
            sensor_type=event.sensor_type, site_id=event.site_id,
            details={"quality": event.quality}
        )
    return None

def stuck_sensor(event: Event, state: DeviceState, cfg) -> Alert | None:
    """Check if sensor value is stuck (no change over time)."""
    if event.msg_type not in ["reading", "telemetry"] or event.value is None:
        state.last_seen_ts = _utc(event.ts)
        return None

    eps = cfg.get("stuck", {}).get("epsilon", 0.1)
    min_run = cfg.get("stuck", {}).get("min_run_length", 6)
    min_dur = cfg.get("stuck", {}).get("min_duration_seconds", 1800)  # Default to 1800 instead of 0!
    
    # Debug log
    if state.last_value is None:
        print(f"[STUCK_SENSOR] Config for {event.device_id}: eps={eps}, min_run={min_run}, min_dur={min_dur}")

    if state.last_value is None:
        state.last_value = event.value
        state.run_length = 1
        state.last_seen_ts = _utc(event.ts)
        state.stuck_since_ts = None
        return None

    if abs(event.value - state.last_value) < eps:
        state.run_length += 1
        if state.stuck_since_ts is None:
            state.stuck_since_ts = _utc(event.ts)
        print(f"[STUCK_SENSOR] Device {event.device_id}: run_length={state.run_length}, value={event.value}, stuck_since={state.stuck_since_ts}")
    else:
        print(f"[STUCK_SENSOR] Device {event.device_id}: value changed {state.last_value} -> {event.value}, resetting run_length")
        state.run_length = 1
        state.stuck_since_ts = None
        state.last_value = event.value

    state.last_seen_ts = _utc(event.ts)

    if state.run_length >= min_run:
        if min_dur <= 0:
            print(f"[STUCK_SENSOR] Device {event.device_id}: ALERT triggered (no min_dur)")
            return Alert(
                device_id=event.device_id, issue_type="stuck_sensor",
                start_ts=state.stuck_since_ts or _utc(event.ts), end_ts=None, severity="warn",
                sensor_type=event.sensor_type, site_id=event.site_id,
                details={"run_length": state.run_length, "epsilon": eps}
            )
        else:
            dur = (_utc(event.ts) - (state.stuck_since_ts or _utc(event.ts))).total_seconds()
            print(f"[STUCK_SENSOR] Device {event.device_id}: run_length={state.run_length} >= {min_run}, dur={dur}s, min_dur={min_dur}s")
            if dur >= min_dur:
                print(f"[STUCK_SENSOR] Device {event.device_id}: ALERT triggered (dur >= min_dur)")
                return Alert(
                    device_id=event.device_id, issue_type="stuck_sensor",
                    start_ts=state.stuck_since_ts, end_ts=None, severity="warn",
                    sensor_type=event.sensor_type, site_id=event.site_id,
                    details={"run_length": state.run_length, "duration_sec": int(dur), "epsilon": eps}
                )
    return None

def silence_checks(event: Event, state: DeviceState, cfg) -> list[Alert]:
    """Check for missing keepalive or prolonged silence alerts."""
    alerts: list[Alert] = []
    now_ts = _utc(event.ts)

    expected = cfg.get("expected_interval_seconds", 60)
    miss_factor = cfg.get("keepalive_miss_factor", 3)
    silence_sec = cfg.get("prolonged_silence_seconds", 1800)

    if state.last_seen_ts is None:
        state.last_seen_ts = now_ts
        return alerts

    gap = (now_ts - state.last_seen_ts).total_seconds()

    if gap >= silence_sec and "prolonged_silence" not in state.open_alerts:
        a = Alert(device_id=event.device_id, issue_type="prolonged_silence",
                  start_ts=state.last_seen_ts, end_ts=None, severity="error",
                  sensor_type=event.sensor_type, site_id=event.site_id,
                  details={"gap_sec": int(gap)})
        state.open_alerts["prolonged_silence"] = a
        alerts.append(a)
    elif gap < silence_sec and "prolonged_silence" in state.open_alerts:
        a = state.open_alerts.pop("prolonged_silence")
        a.end_ts = now_ts
        alerts.append(a)

    miss_thr = miss_factor * expected
    if gap >= miss_thr and gap < silence_sec and "missing_keepalive" not in state.open_alerts:
        a = Alert(device_id=event.device_id, issue_type="missing_keepalive",
                  start_ts=state.last_seen_ts, end_ts=None, severity="critical",
                  sensor_type=event.sensor_type, site_id=event.site_id,
                  details={"gap_sec": int(gap), "expected": expected})
        state.open_alerts["missing_keepalive"] = a
        alerts.append(a)
    elif (gap < miss_thr or gap >= silence_sec) and "missing_keepalive" in state.open_alerts:
        a = state.open_alerts.pop("missing_keepalive")
        a.end_ts = now_ts
        alerts.append(a)

    state.last_seen_ts = now_ts
    return alerts
