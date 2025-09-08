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
            default_radius_px=0.2
        )
