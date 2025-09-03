# from __future__ import annotations
# from PyQt6.QtWebEngineWidgets import QWebEngineView
# from PyQt6.QtCore import QUrl, pyqtSignal
# from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

# class HomeView(QWidget):
#     openAlertsRequested  = pyqtSignal()
#     openSettingsRequested = pyqtSignal()
#     openSensorsRequested = pyqtSignal() 
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

#         base = "http://localhost:3000"  # שנה/י אם גרפנה לא על localhost
#         # פאנלים מתוך הדשבורד sensors.json (uid=agcloud-sensors, panels 1 ו-2)
#         panel_urls = [
#             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=1&from=now-6h&to=now&refresh=10s&theme=light"),
#             QUrl(f"{base}/d-solo/agcloud-sensors/sensors?orgId=1&panelId=2&from=now-6h&to=now&refresh=10s&theme=light"),
#         ]

#         for i, url in enumerate(panel_urls):
#             view = QWebEngineView(self)
#             view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
#             view.setUrl(url)
#             r, c = divmod(i, 2) 
#             grid.addWidget(view, r, c)


from __future__ import annotations
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, pyqtSignal
from PyQt6.QtWidgets import QWidget, QGridLayout, QVBoxLayout, QLabel, QSizePolicy

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

