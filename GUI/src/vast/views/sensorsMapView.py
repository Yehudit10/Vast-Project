
import os
os.environ["QTWEBENGINE_DISABLE_GPU"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-software-rasterizer --disable-webgl"
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTableWidget,
    QPushButton, QTableWidgetItem, QSizePolicy, QFrame
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QTimer, Qt
from dashboard_api import DashboardApi
from pathlib import Path


class SensorsMapView(QWidget):
    """Stable, auto-refreshing sensors dashboard."""
    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api
        self._last_sensor_data = []
        self._map_ready = False
        self._closing = False
        self._visible = False
        self._initialized = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        title = QLabel("🌾 Sensor Dashboard")
        title.setStyleSheet("""
            font-size:22px;
            font-weight:800;
            color:#0f172a;
            margin-bottom:4px;
        """)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignLeft)

        map_frame = QFrame()
        map_layout = QVBoxLayout(map_frame)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)
        map_frame.setStyleSheet("background:#f1f5f9;border-radius:12px;border:1px solid #cbd5e1;")

        self.web = QWebEngineView()
        self.web.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        html_path = Path(__file__).resolve().parent / "assets" / "sensors_map.html"
        self.web.setUrl(QUrl.fromLocalFile(str(html_path)))
        map_layout.addWidget(self.web)
        layout.addWidget(map_frame, stretch=2)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.setStyleSheet("""
            QHeaderView::section {
                background:#e2e8f0;
                color:#0f172a;
                font-weight:700;
                border:none;
                padding:6px 8px;
            }
            QTableWidget {
                background:#ffffff;
                border:1px solid #cbd5e1;
                border-radius:10px;
                gridline-color:#cbd5e1;
                font-size:13px;
            }
            QTableWidget::item { padding:4px 6px; }
        """)
        layout.addWidget(self.table, stretch=1)

        btn = QPushButton("⟳ Load Zone Stats")
        btn.setStyleSheet("""
            QPushButton {
                background:#2563eb;
                color:white;
                font-weight:700;
                padding:8px 14px;
                border-radius:8px;
            }
            QPushButton:hover { background:#1d4ed8; }
            QPushButton:pressed { background:#1e40af; }
        """)
        btn.clicked.connect(self.load_zone_stats)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.web.loadFinished.connect(self._on_map_ready)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_all)

        self._initialized = True

    # --------------------------- Events --------------------------- #
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._map_ready:
            self.web.page().runJavaScript("if (window.map) map.invalidateSize();")
            QTimer.singleShot(800, lambda: self.web.page().runJavaScript("""
                if (window.map) {
                    map.invalidateSize();
                    if (window.image) image.setBounds(map.getBounds());
                }
            """))

    def showEvent(self, event):
        super().showEvent(event)
        self._visible = True
        if not self._closing and not self.timer.isActive():
            self.timer.start(15_000)
        QTimer.singleShot(800, self.refresh_all)

    def hideEvent(self, event):
        self._visible = False
        if self.timer.isActive():
            self.timer.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._closing = True
        self._visible = False
        if self.timer.isActive():
            self.timer.stop()
        super().closeEvent(event)

    # --------------------------- Map --------------------------- #
    def _on_map_ready(self):
        self._map_ready = True
        QTimer.singleShot(800, self._inject_data)

    def _inject_data(self):
        if not self._map_ready or self._closing:
            return
        try:
            token = getattr(self.api, "token", None)
            if not token:
                return

            # --- Fetch zones from DB and render on map ---
            rz = self.api.http.get(f"{self.api.base}/api/tables/zones")
            rz.raise_for_status()
            zones = rz.json().get("rows", [])
            print(zones)
            self.web.page().runJavaScript(f"if (typeof renderZones==='function') renderZones({json.dumps(zones)});")
            self._update_zones(zones)
            # --- Fetch zones from DB and render on map ---
            rz = self.api.http.get(f"{self.api.base}/api/tables/zones")
            rz.raise_for_status()
            zones = rz.json().get("rows", [])
            print(zones)
            self.web.page().runJavaScript(
                f"if (typeof renderZones==='function') renderZones({json.dumps(zones)});"
            )
            self._update_zones(zones)

            r = self.api.http.get(f"{self.api.base}/api/tables/sensor_anomalies")
            r.raise_for_status()
            data = r.json()
            self._update_map(data)
        except Exception as e:
            print("[SensorsView] Failed to inject data:", e)

    def _update_zones(self, zones_data):
        if not self._map_ready or self._closing or not zones_data:
            return
        try:
            js_data = json.dumps(zones_data)
            js = f"""
                if (typeof renderZones === 'function') {{
                    renderZones({js_data});
                }}
            """
            self.web.page().runJavaScript(js)
        except Exception as e:
            print("[SensorsView] Failed to update zones:", e)

    def _update_map(self, sensor_data):
        if not self._map_ready or self._closing or not self._visible:
            return
        rows = sensor_data.get("rows", sensor_data)
        js_data = json.dumps(rows)
        js = f"""
            window.SENSOR_DATA = {js_data};
            if (typeof renderSensors === 'function') {{
                renderSensors(window.SENSOR_DATA);
            }}
            if (window.map) map.invalidateSize();
        """
        self.web.page().runJavaScript(js)

    # --------------------------- Table --------------------------- #
    def load_zone_stats(self):
        if self._closing or not self._initialized or not self._visible:
            return
        try:
            r = self.api.http.get(f"{self.api.base}/api/tables/sensor_zone_stats?limit=10&order_by=inserted_at&order_dir=desc")
            r.raise_for_status()
            data = r.json()
            rows = data.get("rows", data if isinstance(data, list) else [])
        except Exception as e:
            print("[SensorsView] API error:", e)
            self._show_no_data("API Error")
            return

        if not rows:
            self._show_no_data("No data")
            return

        self.table.clear()
        keys = list(rows[0].keys())
        self.table.setColumnCount(len(keys))
        self.table.setHorizontalHeaderLabels(keys)
        self.table.setRowCount(len(rows))

        for r_idx, row in enumerate(rows):
            for c_idx, key in enumerate(keys):
                val = row.get(key, "")
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if not self._closing:
                    self.table.setItem(r_idx, c_idx, item)

        self.table.resizeColumnsToContents()
        self.table.horizontalHeader().setStretchLastSection(True)

    def _show_no_data(self, msg):
        if self._closing:
            return
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(1)
        self.table.setHorizontalHeaderLabels([msg])

    # --------------------------- Refresh --------------------------- #
    def refresh_all(self):
        if self._closing or not self._visible:
            return
        print("[SensorsView] Refreshing data…")
        try:
            self.load_zone_stats()
        except Exception as e:
            print("[SensorsView] refresh error:", e)
            return
        try:
            r = self.api.http.get(f"{self.api.base}/api/tables/sensor_anomalies?limit=10&order_by=inserted_at&order_dir=desc")
            r.raise_for_status()
            data = r.json()
            new_rows = data.get("rows", data)
            if json.dumps(new_rows, sort_keys=True) != json.dumps(self._last_sensor_data, sort_keys=True):
                self._last_sensor_data = new_rows
                self._update_map(data)
            else:
                print("[SensorsView] No sensor changes detected — skipping update.")
        except Exception as e:
            print("[SensorsView] Failed to refresh sensors:", e)
    
