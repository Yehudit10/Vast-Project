import os, json
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTableWidget, QPushButton, QTableWidgetItem, QSizePolicy, QFrame
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QTimer, Qt, pyqtSlot, QObject
from PyQt6.QtWebChannel import QWebChannel
from pathlib import Path
from dashboard_api import DashboardApi

# Disable GPU (useful in Docker)
os.environ["QTWEBENGINE_DISABLE_GPU"] = "1"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-software-rasterizer --disable-webgl"

class JsBridge(QObject):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent

    @pyqtSlot(str)
    def openSensorDetail(self, sensor_id):
        """Called from JS when clicking 'view details'."""
        print(f"[JsBridge] openSensorDetail({sensor_id})")
        # נסרוק עד לחלון העליון (MainWindow) בצורה בטוחה
        try:
            main_window = self.parent.window()
        except Exception:
            main_window = None

        if main_window and hasattr(main_window, "show_sensor_details"):
            main_window.show_sensor_details(sensor_id)

class SensorsMapView(QWidget):
    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api
        self._map_ready = False
        self._visible = False
        self._closing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        title = QLabel("🗺️ Sensor Map")
        title.setStyleSheet("font-size:20px;font-weight:700;color:#0f172a;")
        layout.addWidget(title)

        # Map frame
        map_frame = QFrame()
        map_layout = QVBoxLayout(map_frame)
        map_layout.setContentsMargins(0, 0, 0, 0)
        self.web = QWebEngineView()
        map_layout.addWidget(self.web)
        layout.addWidget(map_frame, stretch=2)

        # Load map HTML
        html_path = Path(__file__).resolve().parent / "assets" / "sensors_map.html"
        self.web.setUrl(QUrl.fromLocalFile(str(html_path)))

        # Stats table
        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, stretch=1)

        btn = QPushButton("⟳ Load Zone Stats")
        btn.setStyleSheet("background:#2563eb;color:white;font-weight:700;padding:8px 14px;border-radius:8px;")
        btn.clicked.connect(self.load_zone_stats)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

        # JS bridge
        self.channel = QWebChannel()
        self.bridge = JsBridge(self)
        self.channel.registerObject("pyObj", self.bridge)
        self.web.page().setWebChannel(self.channel)
        self.web.loadFinished.connect(self._on_map_ready)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_all)

    def _on_map_ready(self):
        self._map_ready = True
        print("[SensorsMapView] Map ready")
        QTimer.singleShot(1000, self._inject_data)

    def _inject_data(self):
          if not self._map_ready:
              return
          try:
              r = self.api.http.get(f"{self.api.base}/api/tables/sensor_anomalies")
              data = r.json()
              js_data = json.dumps(data.get("rows", data))
              js = f"window.SENSOR_DATA={js_data};if(typeof renderSensors==='function')renderSensors(window.SENSOR_DATA);"
              self.web.page().runJavaScript(js)
          except Exception as e:
              print("[SensorsMapView] Error:", e)

    def load_zone_stats(self):
          try:
              r = self.api.http.get(f"{self.api.base}/api/tables/sensor_zone_stats?limit=10&order_by=inserted_at&order_dir=desc")
              rows = r.json().get("rows", [])
          except Exception as e:
              print("[SensorsMapView] API error:", e)
              return

          self.table.clear()
          if not rows:
              self.table.setRowCount(0)
              self.table.setColumnCount(1)
              self.table.setHorizontalHeaderLabels(["No data"])
              return

      
          exclude_keys = {"max", "min", "std", "median","mean"}

          keys = [k for k in rows[0].keys() if k not in exclude_keys]

          self.table.setColumnCount(len(keys))
          self.table.setHorizontalHeaderLabels(keys)
          self.table.setRowCount(len(rows))

          for i, row in enumerate(rows):
              for j, key in enumerate(keys):
                  item = QTableWidgetItem(str(row.get(key, "")))
                  item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                  self.table.setItem(i, j, item)

          self.table.resizeColumnsToContents()
          self.table.horizontalHeader().setStretchLastSection(True)

    def refresh_all(self):
        if self._closing or not self._visible:
            return
        self.load_zone_stats()
        self._inject_data()

    def showEvent(self, event):
        super().showEvent(event)
        self._visible = True
        QTimer.singleShot(1000, self._inject_data)

    def hideEvent(self, event):
        self._visible = False
        super().hideEvent(event)
