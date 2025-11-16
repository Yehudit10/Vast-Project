# core/engine.py

from .state import StateStore
from .types import Event, Alert
from .rules import corrupted, out_of_range, stuck_sensor
from datetime import datetime, timezone
import time

from api.devices_updater import update_device_last_seen
from api.devices_client import get_sensors_last_seen
from api.auth import get_access_token


class Engine:
    def __init__(self, cfg, writer, state: StateStore | None = None):
        """
        cfg: dict read from rules.yaml (includes features/ranges/defaults/stuck)
        writer: either a single object with write(alert) or a list of writers
        """
        self.cfg = cfg
        self.writers = writer if isinstance(writer, (list, tuple)) else [writer]
        self.state = state or StateStore()

        # --- API info & persistent token ---
        self.api_base = "http://host.docker.internal:8001"
        self.token = get_access_token(self.api_base)
        if self.token:
            print("[ENGINE] Access token acquired successfully.")
        else:
            print("[ENGINE][WARN] Failed to get API token at startup.")

    # --- Utilities ---------------------------------------------------------

    def _emit(self, alert: Alert):
        for w in self.writers:
            w.write(alert)

    def _open_once(self, dev_state, alert: Alert):
        """Open an event only if it’s not already open for the same issue_type."""
        if alert.issue_type not in dev_state.open_alerts:
            dev_state.open_alerts[alert.issue_type] = alert
            print(f"[ENGINE] Opening new alert: {alert.issue_type} for device {alert.device_id}")
            self._emit(alert)

    def _close_if_open(self, dev_state, issue_type: str, ts):
        """Close an open event (if exists) and update end_ts."""
        if issue_type in dev_state.open_alerts:
            a = dev_state.open_alerts.pop(issue_type)
            a.end_ts = ts
            print(f"[ENGINE] Closing alert: {issue_type} for device {a.device_id}")
            self._emit(a)

    def _close_all_keepalive_alerts(self, dev_state, ts):
        """Close missing_keepalive alert when sensor sends valid data."""
        print(f"[ENGINE] Checking open alerts before close_all_keepalive_alerts: {list(dev_state.open_alerts.keys())}")
        
        if "missing_keepalive" in dev_state.open_alerts:
            a = dev_state.open_alerts.pop("missing_keepalive")
            a.end_ts = ts
            print(f"[ENGINE] Closing missing_keepalive alert (sensor back online) for {a.device_id}")
            self._emit(a)
        else:
            print(f"[ENGINE] No missing_keepalive alert to close for this device")

    # ----------------------------------------------------------------------

    def sweep_silence(self, now):
        """
        Periodic silence check based on DB 'devices_sensor.last_seen'.
        Checks for missing_keepalive (not prolonged_silence).
        """
        print("[ENGINE] Starting silence sweep (via DB API)...")

        # Fetch sensors via API (single attempt)
        sensors = get_sensors_last_seen(self.api_base, self.token)

        if not sensors:
            print("[ENGINE][ERROR] No sensors retrieved. Skipping silence sweep.")
            return

        expected = self.cfg.get("expected_interval_seconds", 60)
        miss_factor = self.cfg.get("keepalive_miss_factor", 3)
        miss_thr = miss_factor * expected
        print(f"[ENGINE] Checking {len(sensors)} sensors for missing keepalive > {miss_thr}s")

        for s in sensors:
            sensor_id = s.get("id")
            last_seen_str = s.get("last_seen")
            if not sensor_id or not last_seen_str:
                continue

            try:
                last_seen = datetime.fromisoformat(last_seen_str.replace("Z", "+00:00"))
            except Exception:
                print(f"[ENGINE][WARN] Invalid timestamp for {sensor_id}: {last_seen_str}")
                continue

            gap = (now - last_seen).total_seconds()
            
            # Check for missing_keepalive only
            dev_state = self.state.get(sensor_id)
            if dev_state and gap >= miss_thr and "missing_keepalive" not in dev_state.open_alerts:
                alert = Alert(
                    issue_type="missing_keepalive",
                    device_id=sensor_id,
                    sensor_type=s.get("sensor_type", "unknown"),
                    site_id=None,
                    severity="critical",
                    start_ts=last_seen,
                    end_ts=None,
                    details={"gap_sec": int(gap), "expected": expected},
                )
                print(f"[ENGINE] Sensor {sensor_id} missing keepalive for {int(gap)}s — creating alert.")
                dev_state.open_alerts["missing_keepalive"] = alert
                self._emit(alert)
            elif dev_state and gap < miss_thr and "missing_keepalive" in dev_state.open_alerts:
                # Close the alert if gap is back to normal
                alert = dev_state.open_alerts.pop("missing_keepalive")
                alert.end_ts = now
                print(f"[ENGINE] Sensor {sensor_id} keepalive restored — closing alert.")
                self._emit(alert)

    # ----------------------------------------------------------------------

    def process_event(self, ev: Event):
        """Process a single event and manage open/close logic for alerts."""
        print(f"[ENGINE] Processing event: device_id={ev.device_id}, msg_type={ev.msg_type}, sensor_type={ev.sensor_type}")

        if not self.state.is_known_device(ev.device_id):
            print(f"[ENGINE] Unknown device {ev.device_id} - skipping")
            return

        print(f"[ENGINE] Known device {ev.device_id} - processing")
        feats = (self.cfg.get("features") or {})
        dev = self.state.get(ev.device_id)

        # === Step 1: Update device state and DB ===
        print(f"[ENGINE] Updating device {ev.device_id} last_seen_ts from {dev.last_seen_ts} to {ev.ts}")
        dev.last_seen_ts = ev.ts
        dev.last_value = ev.value

        # --- Update API record ---
        update_device_last_seen(ev.device_id)

        if ev.sensor_type and ev.sensor_type != "unknown_sensor":
            dev.sensor_type = ev.sensor_type

        # === Step 2: Close keepalive-related alerts ===
        self._close_all_keepalive_alerts(dev, ev.ts)

        # === Step 3: Corrupted readings ===
        if feats.get("corrupted", True):
            a = corrupted(ev, self.cfg)
            if a:
                print(f"[ENGINE] Corrupted reading detected for device {ev.device_id}")
                self._open_once(dev, a)
                self._close_if_open(dev, "out_of_range", ev.ts)
                self._close_if_open(dev, "stuck_sensor", ev.ts)
                return
        print(f"[ENGINE] No corrupted reading for device {ev.device_id}")

        # === Step 4: Out-of-range checks ===
        if feats.get("out_of_range", True):
            print(f"[ENGINE] Checking out_of_range for device {ev.device_id}, value={ev.value}")
            a = out_of_range(ev, self.cfg)
            if a:
                print(f"[ENGINE] Out-of-range detected for device {ev.device_id}: {a}")
                self._open_once(dev, a)
            else:
                print(f"[ENGINE] Value in range for device {ev.device_id}")
                self._close_if_open(dev, "out_of_range", ev.ts)

        # === Step 5: Stuck sensor checks ===
        if feats.get("stuck_sensor", True):
            print(f"[ENGINE] Checking stuck_sensor for device {ev.device_id}")
            a = stuck_sensor(ev, dev, self.cfg)
            if a:
                print(f"[ENGINE] Stuck sensor detected for device {ev.device_id}")
                self._open_once(dev, a)
            else:
                self._close_if_open(dev, "stuck_sensor", ev.ts)
