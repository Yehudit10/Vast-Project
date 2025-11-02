import yaml
from string import Template
from PyQt6.QtCore import QObject, pyqtSignal
from alert_client import AlertClient
from concurrent.futures import ThreadPoolExecutor

class AlertService(QObject):
    alertsUpdated = pyqtSignal(list)
    alertAdded = pyqtSignal(dict)
    alertRemoved = pyqtSignal(str)

    def __init__(self, ws_url, api, templates_path="src/vast/templates.yml"):
        super().__init__()
        self.api = api
        self.device_locations = {}
        self.templates = self._load_templates(templates_path)
        self.load_devices()

        self.client = AlertClient(ws_url)
        self.client.alertReceived.connect(self._on_realtime)

        self.alerts = []

    # ────────────────────────────────
    # Load YAML templates
    # ────────────────────────────────
    def _load_templates(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                print(f"[AlertService] Loaded templates from {path}")
                return data.get("templates", {})
        except Exception as e:
            print("[AlertService] Failed to load templates:", e)
            return {}

    # ────────────────────────────────
    # Fetch devices from DB
    # ────────────────────────────────
    def load_devices(self):
        try:
            url = f"{self.api.base}/api/tables/devices"
            r = self.api.http.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            devices = data.get("rows", data)

            self.device_locations = {
                d["device_id"]: (d.get("location_lat"), d.get("location_lon"))
                for d in devices if d.get("device_id")
            }
            print(f"[AlertService] Cached {len(self.device_locations)} device locations.")
        except Exception as e:
            print("[AlertService] Failed to fetch devices:", e)

    # ────────────────────────────────
    # Fetch alerts from DB and enrich with templates
    # ────────────────────────────────
    def load_initial(self):
        try:
            url = f"{self.api.base}/api/tables/alerts"
            r = self.api.http.get(url, timeout=10)
            r.raise_for_status()
            data = r.json()
            alerts = data.get("rows", data)

            for a in alerts:
                device_id = a.get("device_id")
                alert_type = a.get("alert_type")

                # Add lat/lon if missing
                if device_id in self.device_locations:
                    lat, lon = self.device_locations[device_id]
                    if not a.get("lat") and lat:
                        a["lat"] = lat
                    if not a.get("lon") and lon:
                        a["lon"] = lon

                # Apply template enrichment
                tmpl = self.templates.get(alert_type)
                if tmpl:
                    a["category"] = tmpl.get("category")
                    context = {
                        "device_id": device_id,
                        "area": a.get("area", "unknown area"),
                        "confidence": a.get("confidence", "?"),
                        "timestamp": a.get("started_at", ""),
                    }
                    # Use Template.safe_substitute to avoid KeyErrors
                    a["summary"] = Template(tmpl.get("summary", "")).safe_substitute(context)
                    a["recommendation"] = Template(tmpl.get("recommendation", "")).safe_substitute(context)

            self.alerts = alerts
            self.alertsUpdated.emit(self.alerts)
            print(f"[AlertService] Loaded {len(alerts)} enriched alerts.")
        except Exception as e:
            print("[AlertService] Failed to fetch alerts:", e)

    # ────────────────────────────────
    # Handle incoming WebSocket alerts
    # ────────────────────────────────
    def _on_realtime(self, alert_msg):
        alerts = alert_msg.get("alerts", [])
        print("[AlertService] Realtime message:", alert_msg)

        for a in alerts:
            labels = a.get("labels", {})
            ann = a.get("annotations", {})
            alert_id = labels.get("alert_id")
            device_id = labels.get("device")
            alert_type = labels.get("alertname")
            ends_at = a.get("endsAt")
            is_resolved = ends_at and not ends_at.startswith("0001-01-01")

            if is_resolved:
                self.alerts = [al for al in self.alerts if al.get("alert_id") != alert_id]
                self.alertRemoved.emit(alert_id)
                continue

            lat = ann.get("lat")
            lon = ann.get("lon")

            # Fill missing coordinates
            if (not lat or not lon) and device_id in self.device_locations:
                lat, lon = self.device_locations[device_id]
                print(f"[AlertService] Filled missing coords for {device_id}: ({lat}, {lon})")

            # Enrich with template
            tmpl = self.templates.get(alert_type, {})
            summary = Template(tmpl.get("summary", "")).safe_substitute(
                device_id=device_id, area=ann.get("area", ""), confidence=ann.get("confidence", "")
            )
            recommendation = tmpl.get("recommendation", "")
            category = tmpl.get("category")

            normalized = {
                "alert_id": alert_id,
                "alert_type": alert_type,
                "device_id": device_id,
                "lat": lat,
                "lon": lon,
                "severity": int(ann.get("severity", 1)),
                "summary": summary,
                "recommendation": recommendation,
                "category": category,
                "hls": ann.get("hls"),
                "vod": ann.get("vod"),
                "image_url": ann.get("image_url"),
                "startsAt": a.get("startsAt"),
            }
            self.alerts.append(normalized)
            self.alertAdded.emit(normalized)
            
    def mark_all_acknowledged(self):
        """Mark all alerts as acknowledged both locally and in DB (PATCH /api/tables/alerts)."""
        unacked = [a for a in self.alerts if not a.get("ack", False)]
        if not unacked:
            return

        # Update local memory first
        for a in unacked:
            a["ack"] = True

        # Push updates asynchronously to DB
        def _patch_ack(alert):
            try:
                url = f"{self.api.base}/api/tables/alerts"
                payload = {
                    "keys": {"alert_id": alert["alert_id"]},
                    "data": {"ack": True},
                }
                r = self.api.http.patch(url, json=payload, timeout=5)
                r.raise_for_status()
            except Exception as e:
                print(f"[AlertService] Failed to PATCH ack for {alert['alert_id']}: {e}")

        with ThreadPoolExecutor(max_workers=4) as pool:
            for a in unacked:
                pool.submit(_patch_ack, a)

        self.alertsUpdated.emit(self.alerts)
        print(f"[AlertService] Marked {len(unacked)} alerts as acknowledged.")
        



