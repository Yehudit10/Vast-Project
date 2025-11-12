from __future__ import annotations
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSizePolicy, QPushButton
)
from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer
from vast.orthophoto_canvas.ui.sensors_layer import SensorLayer, add_sensors_by_gps_bulk
from orthophoto_canvas.ag_io import sensors_api
import os

from vast.orthophoto_canvas.ui.alert_layer import AlertLayer


class HomeView(QWidget):
    openSensorsRequested = pyqtSignal()

    def __init__(self, api, alert_service, parent: QWidget | None = None):
        super().__init__(parent)
        self.api = api
        self.alert_service = alert_service

        # ─────────────────────────────
        # Root vertical layout
        # ─────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        # Header
        header = QLabel("Sensors Dashboard (Grafana)")
        header.setStyleSheet("font-size: 20px; font-weight: 600; margin-bottom: 8px;")
        root.addWidget(header)

        # ─────────────────────────────
        # Main content: Map (left) + Panels (right)
        # ─────────────────────────────
        main_layout = QHBoxLayout()
        main_layout.setSpacing(12)
        root.addLayout(main_layout, stretch=1)

        # ───── Map on the left ─────
        tiles_root = "./src/vast/orthophoto_canvas/data/tiles"
        self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)
        self.viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.viewer.setMinimumSize(700, 700)  # Ensures it's visibly large and square
        main_layout.addWidget(self.viewer, stretch=3)

        # ───── Grafana panels on the right ─────
        right_box = QVBoxLayout()
        right_box.setSpacing(10)
        main_layout.addLayout(right_box, stretch=2)

        grafana_host = os.getenv("GRAFANA_HOST", "grafana")
        base = f"http://{grafana_host}:3000"
        panel_urls = [
            QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
            QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
        ]

        for url in panel_urls:
            view = QWebEngineView(self)
            view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            view.setFixedHeight(300)
            view.setUrl(url)
            right_box.addWidget(view)

        # ─────────────────────────────
        # Load sensors layer
        # ─────────────────────────────
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

        # ─────────────────────────────
        # Alerts layer setup
        # ─────────────────────────────
        self.alert_layer = AlertLayer(self.viewer)
        self.alert_service.alertsUpdated.connect(self._on_alerts_updated)
        self.alert_service.alertAdded.connect(self._on_alert_added)
        self.alert_service.alertRemoved.connect(self._on_alert_removed)
        self.alert_service.load_initial()

        # ─────────────────────────────
        # Footer button
        # ─────────────────────────────
        self.sensor_types_btn = QPushButton("Sensor Types")
        self.sensor_types_btn.setStyleSheet("padding: 8px 12px; font-weight: 500;")
        self.sensor_types_btn.clicked.connect(self.openSensorsRequested.emit)
        root.addWidget(self.sensor_types_btn)

    # ─────────────────────────────
    # Keep the map square on resize
    # ─────────────────────────────
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.viewer:
            # Square size = min(available height, available width fraction)
            left_width = int(self.width() * 0.6)
            height = self.height() - 100
            size = min(left_width, height)
            if size > 400:
                self.viewer.setFixedSize(size-50, size-50)

    # ─────────────────────────────
    # Alerts Handlers
    # ─────────────────────────────
    def _on_alerts_updated(self, alerts: list):
        print(f"[HomeView] Full alert update: {len(alerts)} alerts")

        active_alerts = [a for a in alerts if not a.get("ended_at") and not a.get("endedAt")]
        print(f"[HomeView] Displaying {len(active_alerts)} active alerts on map")

        self.alert_layer.clear_alerts()
        for alert in active_alerts:
            self.alert_layer.add_or_update_alert(alert)

    def _on_alert_added(self, alert: dict):
        print(f"[HomeView] New alert added: {alert.get('alert_id')}")
        self.alert_layer.add_or_update_alert(alert)

    def _on_alert_removed(self, alert_id: str):
        print(f"[HomeView] Removing alert: {alert_id}")
        self.alert_layer.remove_alert(alert_id)

    # ─────────────────────────────
    # Real-time alert normalization
    # ─────────────────────────────
    def _on_alert_realtime(self, alert: dict):
        alerts = alert.get("alerts", [])
        if not alerts:
            print("[HomeView] No alerts in payload.")
            return

        for a in alerts:
            labels = a.get("labels", {})
            ann = a.get("annotations", {})

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
            is_resolved = ended_at and not ended_at.startswith("0001-01-01")

            if is_resolved:
                print(f"[HomeView] Removing resolved alert: {alert_id}")
                self.alert_layer.remove_alert(alert_id)
                continue

            print(f"[HomeView] Active alert: {normalized['alert_type']} "
                  f"from {normalized['device_id']} ({normalized['lat']}, {normalized['lon']})")
            self.alert_layer.add_or_update_alert(normalized)
