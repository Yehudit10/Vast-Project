from __future__ import annotations
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy, QPushButton
from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer
from vast.orthophoto_canvas.ui.sensors_layer import SensorLayer, add_sensors_by_gps_bulk
from orthophoto_canvas.ag_io import sensors_api
import os

from alert_client import AlertClient
from vast.orthophoto_canvas.ui.alert_layer import AlertLayer

class HomeView(QWidget):
    openSensorsRequested = pyqtSignal()

    def __init__(self, api,alert_service, parent: QWidget | None = None):
        super().__init__(parent)
        self.api=api
        self.alert_service=alert_service
        root = QVBoxLayout(self)
        header = QLabel("Sensors Dashboard (Grafana)")
        header.setStyleSheet("font-size: 20px; font-weight: 600;")
        root.addWidget(header)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        root.addLayout(grid)

        grafana_host = os.getenv("GRAFANA_HOST", "grafana")
        base = f"http://{grafana_host}:3000"
        panel_urls = [
            QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
            QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
        ]

        for i, url in enumerate(panel_urls):
            view = QWebEngineView(self)
            view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            view.setUrl(url)
            r, c = divmod(i, 2)
            grid.addWidget(view, r, c)

        tiles_root = "./src/vast/orthophoto_canvas/data/tiles"
        self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)
        grid.addWidget(self.viewer, 1, 0, 1, 2)

        gateway_url = os.getenv("GATEWAY_URL", "http://gateway:8000")
        sensors_api.GATEWAY_URL = gateway_url
        rows = sensors_api.get_sensors()
        self.sensor_layer = SensorLayer(self.viewer)
        add_sensors_by_gps_bulk(
            self.sensor_layer,
            rows,
            center_on_first=True,
            default_radius_px=0.2
        )

        self.alert_layer = AlertLayer(self.viewer)
        alerts = self.fetch_active_alerts()
        for alert in alerts:
            self.alert_layer.add_or_update_alert(alert)

        # Subscribe to centralized AlertService updates
        self.alert_service.alertsUpdated.connect(self._on_alerts_updated)
        self.alert_service.alertAdded.connect(self._on_alert_added)
        self.alert_service.alertRemoved.connect(self._on_alert_removed)

        # Load initial alerts
        self.alert_service.load_initial()

        # print(f"[HomeView] Connected to alerts gateway: {gateway_ws}")

        self.sensor_types_btn = QPushButton("Sensor Types")
        self.sensor_types_btn.clicked.connect(self.openSensorsRequested.emit)
        root.addWidget(self.sensor_types_btn)

    def _on_alerts_updated(self, alerts: list):
        """Called when AlertService emits a full update list."""
        print(f"[HomeView] Full alert update: {len(alerts)} alerts")
        self.alert_layer.clear_alerts()  # assuming you have clear() or reset() on AlertLayer
        for alert in alerts:
            self.alert_layer.add_or_update_alert(alert)

    def _on_alert_added(self, alert: dict):
        """Called when a new alert arrives."""
        print(f"[HomeView] New alert added: {alert.get('alert_id')}")
        self.alert_layer.add_or_update_alert(alert)

    def _on_alert_removed(self, alert_id: str):
        """Called when an alert is resolved/removed."""
        print(f"[HomeView] Removing alert: {alert_id}")
        self.alert_layer.remove_alert(alert_id)

    
    def fetch_active_alerts(self):
        try:
            print("[HomeView] Fetching active alerts from dashboard API...")
            url = f"{self.api.base}/api/tables/alerts"
            r = self.api.http.get(url, timeout=10)
            if r.status_code != 200:
                print(f"[HomeView] Failed to fetch alerts: {r.status_code}")
                return []

            data = r.json()
            # ✅ Unwrap 'rows' if present
            if isinstance(data, dict) and "rows" in data:
                alerts = data["rows"]
            else:
                alerts = data

            print(f"[HomeView] Loaded {len(alerts)} active alerts from DB.")
            return alerts

        except Exception as e:
            print(f"[HomeView] Failed to fetch alerts: {e}")
            return []




    def _on_alert_realtime(self, alert: dict):
        print("[HomeView] Raw alert payload:", alert)

        alerts = alert.get("alerts", [])
        if not alerts:
            print("[HomeView] No alerts in payload.")
            return

        for a in alerts:
            labels = a.get("labels", {})
            ann = a.get("annotations", {})

            # Normalize Alertmanager format to your app format
            normalized = {
                "alert_id": labels.get("alert_id"),
                "alert_type": labels.get("alertname"),
                "device_id": labels.get("device"),
                "lat": float(ann.get("lat")) if ann.get("lat") else None,
                "lon": float(ann.get("lon")) if ann.get("lon") else None,
                "severity": int(ann.get("severity", 1)),
                "confidence": float(ann.get("confidence", 0)),
                "area": ann.get("area"),
                "summary": ann.get("summary"),
                "category": ann.get("category"),
                "recommendation": ann.get("recommendation"),
                "meta": ann.get("meta"),
                "startsAt": a.get("startsAt"),
                "endsAt": a.get("endsAt"),
            }

            alert_id = normalized.get("alert_id")
            ended_at = normalized.get("endsAt")

            # Treat "0001-01-01T00:00:00Z" and None as "not resolved"
            is_resolved = ended_at and not ended_at.startswith("0001-01-01")

            if is_resolved:
                print(f"[HomeView] Removing resolved alert: {alert_id}")
                self.alert_layer.remove_alert(alert_id)
                continue

            print(f"[HomeView] Active alert: {normalized['alert_type']} from {normalized['device_id']} "
                  f"({normalized['lat']}, {normalized['lon']})")
            self.alert_layer.add_or_update_alert(normalized)




