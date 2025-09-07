# # # # # # from __future__ import annotations
# # # # # # from PyQt6.QtWebEngineWidgets import QWebEngineView
# # # # # # from PyQt6.QtCore import QUrl, pyqtSignal
# # # # # # from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

# # # # # # class HomeView(QWidget):
# # # # # #     openAlertsRequested  = pyqtSignal()
# # # # # #     openSettingsRequested = pyqtSignal()
# # # # # #     openSensorsRequested = pyqtSignal() 
# # # # # #     def __init__(self, api, parent: QWidget | None = None):
# # # # # #         super().__init__(parent)

# # # # # #         root = QVBoxLayout(self)

# # # # # #         header = QLabel("Sensors Dashboard (Grafana)")
# # # # # #         header.setStyleSheet("font-size: 20px; font-weight: 600;")
# # # # # #         root.addWidget(header)

# # # # # #         grid = QGridLayout()
# # # # # #         grid.setHorizontalSpacing(12)
# # # # # #         grid.setVerticalSpacing(12)
# # # # # #         root.addLayout(grid)

# # # # # #         base = "http://localhost:3000"  # שנה/י אם גרפנה לא על localhost
# # # # # #         # פאנלים מתוך הדשבורד sensors.json (uid=agcloud-sensors, panels 1 ו-2)
# # # # # #         panel_urls = [
# # # # # #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
# # # # # #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
# # # # # #         ]

# # # # # #         for i, url in enumerate(panel_urls):
# # # # # #             view = QWebEngineView(self)
# # # # # #             view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
# # # # # #             view.setUrl(url)
# # # # # #             r, c = divmod(i, 2) 
# # # # # #             grid.addWidget(view, r, c)


# # # # # from __future__ import annotations
# # # # # from PyQt6.QtWebEngineWidgets import QWebEngineView
# # # # # from PyQt6.QtCore import QUrl, pyqtSignal
# # # # # from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

# # # # # class HomeView(QWidget):
# # # # #     openSensorsRequested    = pyqtSignal()
# # # # #     openAlertsRequested     = pyqtSignal()
# # # # #     openSettingsRequested   = pyqtSignal()
# # # # #     openProcessingRequested = pyqtSignal()
# # # # #     openPredictionsRequested = pyqtSignal() 

# # # # #     def __init__(self, api, parent: QWidget | None = None):
# # # # #         super().__init__(parent)

# # # # #         root = QVBoxLayout(self)
# # # # #         header = QLabel("Sensors Dashboard (Grafana)")
# # # # #         header.setStyleSheet("font-size: 20px; font-weight: 600;")
# # # # #         root.addWidget(header)

# # # # #         grid = QGridLayout()
# # # # #         grid.setHorizontalSpacing(12)
# # # # #         grid.setVerticalSpacing(12)
# # # # #         root.addLayout(grid)

# # # # #         base = "http://localhost:3000"  
# # # # #         panel_urls = [
# # # # #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
# # # # #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
# # # # #             QUrl("http://localhost:8000/map"),  # Map view

# # # # #         ]

# # # # #         for i, url in enumerate(panel_urls):
# # # # #             view = QWebEngineView(self)
# # # # #             view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
# # # # #             view.setUrl(url)
# # # # #             r, c = divmod(i, 2)
# # # # #             grid.addWidget(view, r, c)

# # # # from __future__ import annotations

# # # # # Use PyQt6 (same as orthophoto viewer)
# # # # from PyQt6.QtWebEngineWidgets import QWebEngineView
# # # # from PyQt6.QtCore import QUrl, pyqtSignal
# # # # from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

# # # # # Import the PyQt viewer and sensors glue
# # # # from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer  # :contentReference[oaicite:2]{index=2}
# # # # from orthophoto_canvas.ui.sensors_layer import SensorLayer, add_sensors_by_gps_bulk  # :contentReference[oaicite:3]{index=3}
# # # # from orthophoto_canvas.ag_io import sensors_api  # :contentReference[oaicite:4]{index=4}

# # # # class HomeView(QWidget):
# # # #     openSensorsRequested    = pyqtSignal()
# # # #     openAlertsRequested     = pyqtSignal()
# # # #     openSettingsRequested   = pyqtSignal()
# # # #     openProcessingRequested = pyqtSignal()
# # # #     openPredictionsRequested = pyqtSignal()

# # # #     def __init__(self, api, parent: QWidget | None = None):
# # # #         super().__init__(parent)

# # # #         root = QVBoxLayout(self)
# # # #         header = QLabel("Sensors Dashboard (Grafana)")
# # # #         header.setStyleSheet("font-size: 20px; font-weight: 600;")
# # # #         root.addWidget(header)

# # # #         grid = QGridLayout()
# # # #         grid.setHorizontalSpacing(12)
# # # #         grid.setVerticalSpacing(12)
# # # #         root.addLayout(grid)

# # # #         # --- Grafana panels (unchanged) ---
# # # #         base = "http://localhost:3000"
# # # #         panel_urls = [
# # # #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
# # # #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
# # # #         ]
# # # #         for i, url in enumerate(panel_urls):
# # # #             view = QWebEngineView(self)
# # # #             view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
# # # #             view.setUrl(url)
# # # #             r, c = divmod(i, 2)
# # # #             grid.addWidget(view, r, c)

# # # #         # --- Orthophoto viewer (the exact PyQt map widget) ---
# # # #         tiles_root = "orthophoto_canvas/data/tiles"   # your tiles path
# # # #         self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)
# # # #         self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

# # # #         # put the map large: span two columns under the two Grafana panels
# # # #         grid.addWidget(self.viewer, 1, 0, 1, 2)

# # # #         # --- Real sensors overlay (same source as the viewer app) ---
# # # #         # sensors_api.get_sensors() queries the gateway and returns real sensors (list of dicts)
# # # #         # keys include: sensor_id, lat, lon, status, name, label, battery, moisture, ...
# # # #         rows = sensors_api.get_sensors()  # :contentReference[oaicite:5]{index=5}

# # # #         self.sensor_layer = SensorLayer(self.viewer)
# # # #         add_sensors_by_gps_bulk(
# # # #             self.sensor_layer,
# # # #             rows,
# # # #             center_on_first=True,
# # # #             default_radius_px=0.14
# # # #         )  # draws real sensors with tooltips/hover like in your viewer layer :contentReference[oaicite:6]{index=6}



# # # from __future__ import annotations

# # # from pathlib import Path
# # # from PyQt6.QtCore import QUrl, pyqtSignal
# # # from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy
# # # from PyQt6.QtWebEngineWidgets import QWebEngineView
# # # from PyQt6.QtWebEngineCore import QWebEngineSettings
# # # from PyQt6 import QtWebEngineWidgets  # ensure WebEngine loads

# # # from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer
# # # from orthophoto_canvas.ui.sensors_layer import SensorLayer, add_sensors_by_gps_bulk
# # # from orthophoto_canvas.ag_io import sensors_api


# # # def _graf_base() -> str:
# # #     """
# # #     Resolve Grafana base URL. If you later want to make it configurable,
# # #     you can read from an env var here.
# # #     """
# # #     return "http://localhost:3000"


# # # def _panel_url(panel_id: int) -> QUrl:
# # #     # d-solo loads a single panel. 'kiosk' removes Grafana chrome.
# # #     url = f"{_graf_base()}/d-solo/agcloud-sensors/sensors" \
# # #           f"?orgId=1&panelId={panel_id}&from=now-6h&to=now&refresh=10s&theme=light&kiosk"
# # #     return QUrl(url)


# # # class HomeView(QWidget):
# # #     openSensorsRequested    = pyqtSignal()
# # #     openAlertsRequested     = pyqtSignal()
# # #     openSettingsRequested   = pyqtSignal()
# # #     openProcessingRequested = pyqtSignal()
# # #     openPredictionsRequested = pyqtSignal()

# # #     def __init__(self, api, parent: QWidget | None = None):
# # #         super().__init__(parent)

# # #         root = QVBoxLayout(self)
# # #         header = QLabel("Sensors Dashboard (Grafana)")
# # #         header.setStyleSheet("font-size: 20px; font-weight: 600;")
# # #         root.addWidget(header)

# # #         grid = QGridLayout()
# # #         grid.setHorizontalSpacing(12)
# # #         grid.setVerticalSpacing(12)
# # #         root.addLayout(grid)

# # #         # --- Grafana panels ---
# # #         self.graf_left = QWebEngineView(self)
# # #         self.graf_right = QWebEngineView(self)
# # #         for v in (self.graf_left, self.graf_right):
# # #             v.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
# # #             s = v.settings()
# # #             s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
# # #             s.setAttribute(QWebEngineSettings.AutoLoadImages, True)
# # #             # Important for cases where the HTML is local and Grafana is remote
# # #             s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)

# # #         self.graf_left.setUrl(_panel_url(1))
# # #         self.graf_right.setUrl(_panel_url(2))

# # #         grid.addWidget(self.graf_left, 0, 0)
# # #         grid.addWidget(self.graf_right, 0, 1)

# # #         # --- Orthophoto viewer (exact same widget as the standalone app) ---
# # #         tiles_root = str(Path(__file__).resolve().parent / "orthophoto_canvas" / "data" / "tiles")
# # #         self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)
# # #         self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
# # #         grid.addWidget(self.viewer, 1, 0, 1, 2)  # span two columns

# # #         # --- Real sensors overlay (same source as the viewer app) ---
# # #         rows = sensors_api.get_sensors()
# # #         self.sensor_layer = SensorLayer(self.viewer)
# # #         add_sensors_by_gps_bulk(
# # #             self.sensor_layer,
# # #             rows,
# # #             center_on_first=True,
# # #             default_radius_px=0.14,
# # #         )



# # from __future__ import annotations

# # from PyQt6.QtCore import QUrl, pyqtSignal
# # from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy
# # from PyQt6.QtWebEngineWidgets import (
# #     QWebEngineView,
# #     QWebEngineSettings,
# #     QWebEngineProfile,
# # )

# # # Orthophoto viewer + sensors overlay
# # from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer
# # from orthophoto_canvas.ui.sensors_layer import SensorLayer, add_sensors_by_gps_bulk
# # from orthophoto_canvas.ag_io import sensors_api
# # # --- Grafana panels (robust QWebEngine setup) ---
# # from PyQt6.QtWebEngineWidgets import QWebEngineView, QWebEngineSettings

# # def _new_grafana_panel(url: QUrl, parent: QWidget) -> QWebEngineView:
# #     """Create a QWebEngineView with sane defaults for Grafana embeds."""
# #     view = QWebEngineView(parent)
# #     view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

# #     # Make sure the web view can load and render Grafana
# #     s = view.settings()
# #     for attr in (
# #         QWebEngineSettings.JavascriptEnabled,
# #         QWebEngineSettings.PluginsEnabled,
# #         QWebEngineSettings.WebGLEnabled,
# #         QWebEngineSettings.Accelerated2dCanvasEnabled,
# #         QWebEngineSettings.LocalStorageEnabled,
# #         QWebEngineSettings.ErrorPageEnabled,
# #         QWebEngineSettings.AutoLoadImages,
# #         QWebEngineSettings.LocalContentCanAccessFileUrls,
# #         QWebEngineSettings.LocalContentCanAccessRemoteUrls,
# #     ):
# #         s.setAttribute(attr, True)

# #     # Persistent cookies help if Grafana requires a session
# #     profile = QWebEngineProfile.defaultProfile()
# #     profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

# #     view.setUrl(url)
# #     return view


# # class HomeView(QWidget):
# #     openSensorsRequested = pyqtSignal()
# #     openAlertsRequested = pyqtSignal()
# #     openSettingsRequested = pyqtSignal()
# #     openProcessingRequested = pyqtSignal()
# #     openPredictionsRequested = pyqtSignal()

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

# #         # Grafana panels
# #         base = "http://localhost:3000"
# #         urls = [
# #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors"
# #                  f"?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
# #             QUrl(f"{base}/d-solo/agcloud-sensors/sensors"
# #                  f"?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
# #         ]
# #         for i, url in enumerate(urls):
# #             r, c = divmod(i, 2)
# #             grid.addWidget(_new_grafana_panel(url, self), r, c)

# #         # Orthophoto viewer
# #         tiles_root = "orthophoto_canvas/data/tiles"
# #         self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)
# #         self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
# #         grid.addWidget(self.viewer, 1, 0, 1, 2)

# #         # Real sensors overlay
# #         rows = sensors_api.get_sensors()
# #         self.sensor_layer = SensorLayer(self.viewer)
# #         add_sensors_by_gps_bulk(
# #             self.sensor_layer,
# #             rows,
# #             center_on_first=True,
# #             default_radius_px=0.14,
# #         )


# from __future__ import annotations

# from PyQt6.QtCore import QUrl, pyqtSignal
# from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy
# from PyQt6.QtWebEngineWidgets import (
#     QWebEngineView,
#     QWebEngineSettings,
#     QWebEngineProfile,
# )

# from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer
# from orthophoto_canvas.ui.sensors_layer import SensorLayer, add_sensors_by_gps_bulk
# from orthophoto_canvas.ag_io import sensors_api


# def _make_grafana_panel(url: QUrl, parent: QWidget) -> QWebEngineView:
#     """Create a QWebEngineView ready to embed a Grafana panel."""
#     view = QWebEngineView(parent)
#     view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

#     s = view.settings()
#     for attr in (
#         QWebEngineSettings.JavascriptEnabled,
#         QWebEngineSettings.PluginsEnabled,
#         QWebEngineSettings.WebGLEnabled,
#         QWebEngineSettings.Accelerated2dCanvasEnabled,
#         QWebEngineSettings.LocalStorageEnabled,
#         QWebEngineSettings.ErrorPageEnabled,
#         QWebEngineSettings.AutoLoadImages,
#         QWebEngineSettings.LocalContentCanAccessFileUrls,
#         QWebEngineSettings.LocalContentCanAccessRemoteUrls,
#     ):
#         s.setAttribute(attr, True)

#     # Persist cookies; some Grafana setups rely on a session cookie
#     profile = QWebEngineProfile.defaultProfile()
#     profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

#     # UA that mimics Chrome to avoid UA-sniff glitches
#     profile.setHttpUserAgent(
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#         "AppleWebKit/537.36 (KHTML, like Gecko) "
#         "Chrome/122.0.0.0 Safari/537.36"
#     )

#     view.setUrl(url)
#     return view


# class HomeView(QWidget):
#     openSensorsRequested = pyqtSignal()
#     openAlertsRequested = pyqtSignal()
#     openSettingsRequested = pyqtSignal()
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

#         # --- Grafana panels ---
#         base = "http://127.0.0.1:3000"
#         panel_urls = [
#             QUrl(f"{base}/d-solo/agcloud-sensors/sensors"
#                  f"?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light&kiosk"),
#             QUrl(f"{base}/d-solo/agcloud-sensors/sensors"
#                  f"?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light&kiosk"),
#         ]
#         for i, url in enumerate(panel_urls):
#             r, c = divmod(i, 2)
#             grid.addWidget(_make_grafana_panel(url, self), r, c)

#         # --- Orthophoto viewer ---
#         tiles_root = "orthophoto_canvas/data/tiles"
#         self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)
#         self.viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
#         grid.addWidget(self.viewer, 1, 0, 1, 2)

#         # --- Real sensors overlay ---
#         rows = sensors_api.get_sensors()
#         self.sensor_layer = SensorLayer(self.viewer)
#         add_sensors_by_gps_bulk(
#             self.sensor_layer,
#             rows,
#             center_on_first=True,
#             default_radius_px=0.14,
#         )


from __future__ import annotations

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

# Map viewer (PyQt6 version)
from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer
from orthophoto_canvas.ui.sensors_layer import SensorLayer, add_sensors_by_gps_bulk
from orthophoto_canvas.ag_io import sensors_api

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

        # --- Grafana panels (top row) ---
        base = "http://localhost:3000"
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

        # --- Map viewer (bottom row; spans two columns) ---
        tiles_root = "./orthophoto_canvas/data/tiles"
        self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)
        grid.addWidget(self.viewer, 1, 0, 1, 2)

        # Real sensors overlay
        rows = sensors_api.get_sensors()
        self.sensor_layer = SensorLayer(self.viewer)
        add_sensors_by_gps_bulk(
            self.sensor_layer,
            rows,
            center_on_first=True,
            default_radius_px=0.14
        )
