from PyQt6.QtWidgets import (  
    QVBoxLayout, QWidget
)

from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl

class NotificationView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        web_view = QWebEngineView(self)
        
        notification_api_url = "http://notification_api:5000"
        print(f"[NotificationView] Loading URL: {notification_api_url}")
        web_view.setUrl(QUrl(notification_api_url))
        
        layout.addWidget(web_view)