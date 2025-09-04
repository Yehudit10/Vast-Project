# # from __future__ import annotations
# # from PyQt6.QtWebEngineWidgets import QWebEngineView
# # from PyQt6.QtCore import QUrl, pyqtSignal
# # from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

# # class HomeView(QWidget):
# #     openAlertsRequested  = pyqtSignal()
# #     openSettingsRequested = pyqtSignal()
# #     openSensorsRequested = pyqtSignal() 
# #     def __init__(self, api, parent: QWidget | None = None):
# #         super().__init__(parent)

# #         root = QVBoxLayout(self)

# #         header = QLabel("Sensors Dashboard (Grafana)")
# #         header.setStyleSheet("font-size: 20px; font-weight: 600;")
# #         root.addWidget(header)

# #         grid = QGridLayout()
# #         grid.setHorizontalSpacing(12)
# #         grid.setVerticalSpacing(12)
# #         root.addLayout(grid)

# #         base = "http://localhost:3000"  # שנה/י אם גרפנה לא על localhost
# #         # פאנלים מתוך הדשבורד sensors.json (uid=agcloud-sensors, panels 1 ו-2)
# #         panel_urls = [
# #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
# #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
# #         ]

# #         for i, url in enumerate(panel_urls):
# #             view = QWebEngineView(self)
# #             view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
# #             view.setUrl(url)
# #             r, c = divmod(i, 2) 
# #             grid.addWidget(view, r, c)


# from __future__ import annotations
# from PyQt6.QtWebEngineWidgets import QWebEngineView
# from PyQt6.QtCore import QUrl, pyqtSignal
# from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

# class HomeView(QWidget):
#     openSensorsRequested    = pyqtSignal()
#     openAlertsRequested     = pyqtSignal()
#     openSettingsRequested   = pyqtSignal()
#     openProcessingRequested = pyqtSignal()
#     openPredictionsRequested = pyqtSignal() 

#     def __init__(self, api, parent: QWidget | None = None):
#         super().__init__(parent)

#         root = QVBoxLayout(self)
#         header = QLabel("Sensors Dashboard (Grafana)")
#         header.setStyleSheet("font-size: 20px; font-weight: 600;")
#         root.addWidget(header)

#         grid = QGridLayout()
#         grid.setHorizontalSpacing(12)
#         grid.setVerticalSpacing(12)
#         root.addLayout(grid)

#         base = "http://localhost:3000"  
#         panel_urls = [
#             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
#             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
#             QUrl("http://localhost:8000/map"),  # Map view

#         ]

#         for i, url in enumerate(panel_urls):
#             view = QWebEngineView(self)
#             view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
#             view.setUrl(url)
#             r, c = divmod(i, 2)
#             grid.addWidget(view, r, c)

from __future__ import annotations

# Use PyQt5 (same as orthophoto viewer)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import QUrl, pyqtSignal
from PyQt5.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

# Import the PyQt viewer and sensors glue
from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer  # :contentReference[oaicite:2]{index=2}
from orthophoto_canvas.ui.sensors_layer import SensorLayer, add_sensors_by_gps_bulk  # :contentReference[oaicite:3]{index=3}
from orthophoto_canvas.ag_io import sensors_api  # :contentReference[oaicite:4]{index=4}

class HomeView(QWidget):
    openSensorsRequested    = pyqtSignal()
    openAlertsRequested     = pyqtSignal()
    openSettingsRequested   = pyqtSignal()
    openProcessingRequested = pyqtSignal()
    openPredictionsRequested = pyqtSignal()

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

        # --- Grafana panels (unchanged) ---
        base = "http://localhost:3000"
        panel_urls = [
            QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
            QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
        ]
        for i, url in enumerate(panel_urls):
            view = QWebEngineView(self)
            view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            view.setUrl(url)
            r, c = divmod(i, 2)
            grid.addWidget(view, r, c)

        # --- Orthophoto viewer (the exact PyQt map widget) ---
        tiles_root = "orthophoto_canvas/data/tiles"   # your tiles path
        self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)
        self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # put the map large: span two columns under the two Grafana panels
        grid.addWidget(self.viewer, 1, 0, 1, 2)

        # --- Real sensors overlay (same source as the viewer app) ---
        # sensors_api.get_sensors() queries the gateway and returns real sensors (list of dicts)
        # keys include: sensor_id, lat, lon, status, name, label, battery, moisture, ...
        rows = sensors_api.get_sensors()  # :contentReference[oaicite:5]{index=5}

        self.sensor_layer = SensorLayer(self.viewer)
        add_sensors_by_gps_bulk(
            self.sensor_layer,
            rows,
            center_on_first=True,
            default_radius_px=0.14
        )  # draws real sensors with tooltips/hover like in your viewer layer :contentReference[oaicite:6]{index=6}
