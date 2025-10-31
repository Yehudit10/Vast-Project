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

    def __init__(self, api, parent: QWidget | None = None):
        super().__init__(parent)

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

        gateway_ws = os.getenv("ALERTS_WS", "ws://alerts-gateway:8000/ws/alerts")
        print("ALERTS_WS =", os.getenv("ALERTS_WS"))
        self.alert_client = AlertClient(gateway_ws, self)
        self.alert_client.snapshotReceived.connect(self._on_alert_snapshot)
        self.alert_client.alertReceived.connect(self._on_alert_realtime)

        print(f"[HomeView] Connected to alerts gateway: {gateway_ws}")

        self.sensor_types_btn = QPushButton("Sensor Types")
        self.sensor_types_btn.clicked.connect(self.openSensorsRequested.emit)
        root.addWidget(self.sensor_types_btn)

    def _on_alert_snapshot(self, items: list):
        print(f"[HomeView] Received {len(items)} active alerts (snapshot).")
        self.alert_layer.clear_alerts()
        for alert in items:
            self.alert_layer.add_or_update_alert(alert)

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




