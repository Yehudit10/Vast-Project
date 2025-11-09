from __future__ import annotations
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QPoint
from PyQt6.QtWidgets import (
    QMainWindow, QDockWidget, QListWidget, QListWidgetItem, QStatusBar, QStackedWidget,
    QVBoxLayout, QWidget, QToolButton, QLabel, QHBoxLayout
)
from PyQt6.QtGui import QAction, QIcon
from home_view import HomeView
from views.sensors_view import SensorsView
from views.security.incident_player_vlc import IncidentPlayerVLC
from views.alerts_panel import AlertsPanel
from views.notification_view import NotificationView
from views.fruits_view import FruitsView
from views.ground_view import GroundView
from dashboard_api import DashboardApi
from vast.alerts.alert_service import AlertService
import os


class MainWindow(QMainWindow):
    logoutRequested = pyqtSignal()

    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.setWindowTitle("VAST – Dashboard")
        self.resize(1100, 700)
        self.api = api

        # ---------- Menu ----------
        file_menu = self.menuBar().addMenu("&File")

        # Back
        self.back_action = QAction(QIcon.fromTheme("go-previous"), "Back", self)
        self.back_action.setShortcut("Alt+Left")
        self.back_action.triggered.connect(self.go_back)
        file_menu.addAction(self.back_action)

        # Logout
        self.logout_action = QAction(QIcon.fromTheme("system-log-out"), "Log out", self)
        self.logout_action.triggered.connect(self._logout)
        file_menu.addAction(self.logout_action)

        # ---------- Toolbar ----------
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.addAction(self.back_action)
        toolbar.addAction(self.logout_action)
        toolbar.addSeparator()

        # ---------- Alert Bell Button ----------
        self.alert_button = QToolButton()
        self.alert_button.setToolTip("Show alerts")
        self.alert_button.setText("🔔")
        self.alert_button.setIconSize(QSize(32,32))
        self.alert_button.setStyleSheet("""
            QToolButton {
                border: none;
                background: transparent;
                padding: 4px;
                font-size: 20px;
            }
            QToolButton:hover {
                background-color: #f0f0f0;
                border-radius: 6px;
            }
        """)

        # --- Badge overlay ---
        self.alert_badge = QLabel("0", self.alert_button)
        self.alert_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alert_badge.setFixedSize(18,18)
        self.alert_badge.setFixedSize(14, 14)  # smaller badge
        self.alert_badge.setStyleSheet("""
            QLabel {
                background-color: #1976D2;
                color: white;
                font-size: 8pt;
                font-weight: bold;
                border-radius: 7px;  /* half of size = perfect circle */
                border: 1px solid white;
            }
        """)

        self.alert_badge.hide()

        # Keep badge positioned on the top-right corner
        def reposition_badge():
            btn_w = self.alert_button.width()
            btn_h = self.alert_button.height()
            # move badge to bottom-right corner of bell
            self.alert_badge.move(btn_w - 16, btn_h - 18)
            self.alert_badge.raise_()

        self.alert_button.resizeEvent = lambda e: (
            QToolButton.resizeEvent(self.alert_button, e),
            reposition_badge()
        )
        reposition_badge()

        # Add bell to toolbar
        toolbar.addWidget(self.alert_button)

        # ---------- Navigation Dock ----------
        self.nav_dock = QDockWidget("Navigation", self)
        self.nav_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.nav_dock)

        self.nav_list = QListWidget(self.nav_dock)
        self.nav_dock.setWidget(self.nav_list)

        for name in [
            "Home", "Sensors", "Sound", "Ground Image",
            "Aerial Image", "Fruits", "Security", "Settings", "Notifications"
        ]:
            QListWidgetItem(name, self.nav_list)

        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._on_nav_change)

        # ---------- Alert Service ----------
        ws_url = os.getenv("ALERTS_WS", "ws://alerts-gateway:8000/ws/alerts")
        self.alert_service = AlertService(ws_url, api)
        self.alert_service.alertsUpdated.connect(self.update_alert_badge)
        self.alert_service.alertAdded.connect(lambda _: self.update_alert_badge())

        # ---------- Alerts Panel ----------
        self.alerts_panel = AlertsPanel(self.alert_service)
        self.alerts_panel.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.alerts_panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.alerts_panel.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 1px solid #ccc;
                border-radius: 10px;
            }
        """)
        self.alerts_panel.hide()

        self.alert_button.clicked.connect(self.toggle_alert_panel)

        # ---------- Views ----------
        self.home = HomeView(api, self.alert_service, self)
        self.sensors_view = SensorsView(api, self)
        self.notification_view = NotificationView(self)
        self.fruits_view = FruitsView(api, self)
        self.ground_view = GroundView(api, self)    
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.views = {
            "Home": self.home,
            "Sensors": self.sensors_view,
            "Notifications": self.notification_view,
            "Fruits": self.fruits_view,
            "Ground Image": self.ground_view
        }

        for view in self.views.values():
            self.stack.addWidget(view)

        self.stack.setCurrentWidget(self.home)
        self.history: list = []

        # ---------- Status bar ----------
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        sb.showMessage("Ready")

    # ---------- Alert Badge Management ----------
    def update_alert_badge(self):
        """Show unread (unacknowledged) alert count."""
        unacked = sum(1 for a in self.alert_service.alerts if not a.get("ack", False))
        if unacked > 0:
            self.alert_badge.setText(str(unacked))
            self.alert_badge.show()
        else:
            self.alert_badge.hide()

    def toggle_alert_panel(self):
        """Show or hide the floating AlertsPanel directly below the bell icon."""
        if self.alerts_panel.isVisible():
            self.alerts_panel.hide()
            return

        panel_width = 400
        panel_height = 520
        self.alerts_panel.resize(panel_width, panel_height)

        # Compute position of bell in global coords
        rect = self.alert_button.geometry()
        bottom_left = self.alert_button.mapToGlobal(rect.bottomLeft())
        bottom_right = self.alert_button.mapToGlobal(rect.bottomRight())
        center_x = (bottom_left.x() + bottom_right.x()) // 2 - (panel_width // 2)
        pos_y = bottom_left.y() + 6

        self.alerts_panel.move(center_x, pos_y)
        self.alerts_panel.show()
        self.alerts_panel.raise_()

        # Mark alerts as acknowledged
        if hasattr(self.alert_service, "mark_all_acknowledged"):
            self.alert_service.mark_all_acknowledged()
        self.update_alert_badge()

    # ---------- Navigation ----------
    def _on_nav_change(self, row: int) -> None:
        name = self.nav_list.item(row).text()
        print(f"[MainWindow] Navigation changed to: {name}")
        if name in self.views:
            self.navigate_to(self.views[name])
        else:
            self.statusBar().showMessage(f"Section '{name}' not implemented yet.")

    def navigate_to(self, widget):
        current = self.stack.currentWidget()
        if current not in self.history:
            self.history.append(current)
        self.stack.setCurrentWidget(widget)

    def go_back(self):
        if self.history:
            last = self.history.pop()
            self.stack.setCurrentWidget(last)
        else:
            self.statusBar().showMessage("No previous view to go back to.")

    def _logout(self) -> None:
        self.statusBar().showMessage("Logged out (demo)")
        self.logoutRequested.emit()
