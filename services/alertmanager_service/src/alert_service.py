from __future__ import annotations
import yaml, json, logging, string
from typing import Dict, Any, Sequence
from datetime import datetime, timezone
import urllib.request

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


# ─────────────────────────────────────────────
# Template Renderer
# ─────────────────────────────────────────────
class AlertTemplateRenderer:
    def __init__(self, cfg_path: str):
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        self.templates = cfg.get("templates", {})

    def render(self, alert_type: str, context: dict) -> dict:
        tpl = self.templates.get(alert_type)
        if not tpl:
            raise ValueError(f"No template found for alert type '{alert_type}'")
        return {k: string.Template(str(v)).safe_substitute(context) for k, v in tpl.items()}


# ─────────────────────────────────────────────
# Alertmanager HTTP Client
# ─────────────────────────────────────────────
class AlertmanagerClient:
    def __init__(self, base_url: str, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def send(self, alerts: Sequence[Dict[str, Any]]) -> None:
        """Send alerts to Alertmanager v2 API endpoint."""
        url = f"{self.base_url}/api/v2/alerts"
        data = json.dumps(list(alerts)).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                log.info(f"[Alertmanager] Sent alerts (HTTP {resp.status})")
        except Exception as e:
            log.error(f"[Alertmanager] Failed to send: {e}")
            raise


# ─────────────────────────────────────────────
# Main Service Logic
# ─────────────────────────────────────────────
class AlertManagerService:
    def __init__(self, cfg_path: str, alertmanager_url: str):
        self.renderer = AlertTemplateRenderer(cfg_path)
        self.client = AlertmanagerClient(alertmanager_url)

    def process_alert(self, data: dict):
        """Validate, render, and send an alert to Alertmanager."""
        required_fields = ["alert_id", "alert_type", "device_id", "started_at", "lat", "lon"]
        for field in required_fields:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

        tpl = self.renderer.render(data["alert_type"], data)

        # ───── Stable labels ─────
        labels = {
            "alertname": data["alert_type"],
            "alert_id": data["alert_id"],
            "device": data["device_id"],
        }

        # ───── Descriptive annotations ─────
        annotations = {
            "summary": tpl.get("summary"),
            "recommendation": tpl.get("recommendation"),
            "category": tpl.get("category"),
            "severity": str(data.get("severity", tpl.get("severity", "unknown"))),
        }

        # Optional dynamic fields
        optional_fields = [
            "confidence", "area", "lat", "lon",
            "image_url", "vod", "hls", "meta"
        ]
        for f in optional_fields:
            if f in data and data[f] is not None:
                annotations[f] = str(data[f])

        # ───── Timestamp normalization ─────
        def to_utc_iso(s: str | None) -> str | None:
            if not s:
                return None
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

        starts_at = to_utc_iso(data.get("started_at"))
        ends_at = to_utc_iso(data.get("ended_at"))

        now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        if starts_at and starts_at > now_utc:
            log.warning(f"Start time {starts_at} is in the future, adjusting to now: {now_utc}")
            starts_at = now_utc


        payload = {
            "labels": labels,
            "annotations": annotations,
            "startsAt": starts_at,
        }
        if ends_at:
            payload["endsAt"] = ends_at

        # ───── Send to Alertmanager ─────
        self.client.send([payload])
        log.info(f"[ALERT PAYLOAD] {json.dumps(payload, indent=2)}")

        return payload
