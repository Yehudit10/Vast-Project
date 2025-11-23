from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QMainWindow, QDockWidget, QListWidget, QListWidgetItem, QStatusBar,
    QStackedWidget, QToolButton, QLabel, QWidget, QHBoxLayout, QVBoxLayout,
    QGraphicsDropShadowEffect, QPushButton
)
from PyQt6.QtGui import QAction, QIcon, QFont, QColor
import os

from home_view import HomeView
from views.sensors_view import SensorsView
from views.alerts_panel import AlertsPanel
from views.notification_view import NotificationView
from views.fruits_view import FruitsView
from views.ground_view import GroundView
from views.auth_status_view import AuthStatusView
from dashboard_api import DashboardApi
from vast.alerts.alert_service import AlertService

# === New Sensors GUI imports ===
from views.sensorsMainView import SensorsMainView
from views.sensorsMapView import SensorsMapView
from views.sensorDetailsTab import SensorDetailsTab
from views.sensors_status_summary import SensorsStatusSummary

# === Irrigation imports ===
from views.irrigation.irrigation_view import IrrigationView


class MainWindow(QMainWindow):
    logoutRequested = pyqtSignal()

    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AgCloud – Dashboard")
        self.resize(1280, 760)
        self.api = api

        # ───────────────────────────────
        # GLOBAL STYLE
        # ───────────────────────────────
        self.setStyleSheet("""
            QMainWindow { background-color: #f9fafb; }
            QMenuBar { background-color: #e5e7eb; font-size: 11.5pt; padding: 4px 10px; }
            QToolBar {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f3f4f6);
                border-bottom: 1px solid #d1d5db; padding: 2px 10px; min-height: 42px;
            }
            QToolButton { background-color: transparent; border: none; padding: 4px; border-radius: 8px; font-size: 20px; }
            QToolButton:hover { background-color: #e5e7eb; }
            QListWidget { background-color: #ffffff; border: none; font-size: 12pt; color: #111827; }
            QListWidget::item { padding: 10px; border-radius: 6px; }
            QListWidget::item:selected { background-color: #10b981; color: white; }
            QStatusBar { background-color: #f3f4f6; font-size: 10pt; }
        """)

        # ───────────────────────────────
        # MENU
        # ───────────────────────────────
        file_menu = self.menuBar().addMenu("&File")
        self.back_action = QAction(QIcon.fromTheme("go-previous"), "Back", self)
        self.back_action.setShortcut("Alt+Left")
        self.back_action.triggered.connect(self.go_back)
        file_menu.addAction(self.back_action)
        self.logout_action = QAction("Log out", self)
        self.logout_action.triggered.connect(self._logout)
        file_menu.addAction(self.logout_action)

        # ───────────────────────────────
        # TOP BAR (toolbar)
        # ───────────────────────────────
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(32, 32))

        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(8, 0, 8, 0)
        top_bar_layout.setSpacing(10)

        # Logout button
        logout_btn = QPushButton("Logout")
        logout_btn.setToolTip("Log out")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #10b981;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 6px 16px;
                font-size: 11pt;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #059669; }
            QPushButton:pressed { background-color: #047857; }
        """)
        logout_btn.clicked.connect(self._logout)

        # Alert bell
        self.alert_button = QToolButton()
        self.alert_button.setToolTip("Show alerts")
        self.alert_button.setText("🔔")
        self.alert_button.setIconSize(QSize(40, 40))
        self.alert_button.setStyleSheet("""
            QToolButton {
                font-size: 30px;
                border: none;
                background: transparent;
                padding: 4px;
                border-radius: 8px;
            }
            QToolButton:hover { background-color: #e5e7eb; }
        """)

        # Alert badge
        self.alert_badge = QLabel("0", self.alert_button)
        self.alert_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.alert_badge.setFixedSize(24, 24)
        self.alert_badge.setStyleSheet("""
            QLabel {
                background-color: #3b82f6;
                color: white;
                font-size: 10pt;
                font-weight: bold;
                border-radius: 12px;
                border: 2px solid white;
            }
        """)
        self.alert_badge.hide()

        def reposition_badge():
            btn_w = self.alert_button.width()
            self.alert_badge.move(btn_w - 22, 2)
            self.alert_badge.raise_()

        self.alert_button.resizeEvent = lambda e: (
            QToolButton.resizeEvent(self.alert_button, e),
            reposition_badge()
        )
        reposition_badge()

        # ───────────────────────────────
        # TITLE AREA (Updated)
        # ───────────────────────────────
        title_container = QWidget()
        title_layout = QVBoxLayout(title_container)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)

        main_title = QLabel("AgCloud")
        main_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_title.setStyleSheet("""
            QLabel {
                font-size: 22pt;
                font-weight: 700;
                color: #047857;
                letter-spacing: 1px;
            }
        """)

        subtitle = QLabel("The Smart Platform that Protects and Optimizes Your Field")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("""
            QLabel {
                font-size: 11pt;
                font-weight: 500;
                color: #374151;
                margin-top: 2px;
            }
        """)

        title_layout.addWidget(main_title)
        title_layout.addWidget(subtitle)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(8)
        shadow.setColor(QColor(0, 0, 0, 35))
        shadow.setOffset(0, 2)
        top_bar.setGraphicsEffect(shadow)

        top_bar_layout.addWidget(logout_btn)
        top_bar_layout.addWidget(self.alert_button)
        top_bar_layout.addStretch()
        top_bar_layout.addWidget(title_container)
        top_bar_layout.addStretch()
        toolbar.addWidget(top_bar)

        # ───────────────────────────────
        # NAVIGATION
        # ───────────────────────────────
        self.nav_dock = QDockWidget("Navigation", self)
        self.nav_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.nav_dock)
        self.nav_list = QListWidget(self.nav_dock)
        self.nav_dock.setWidget(self.nav_list)
        self.nav_dock.setMinimumWidth(220)

        font = QFont(); font.setPointSize(12)
        self.nav_list.setFont(font)

        for main_item in ["Home", "Sensors", "Sound", "Ground Image", "Aerial Image", "Fruits", "Irrigation", "Security", "Settings", "Notifications", "Auth"]:
            item = QListWidgetItem(main_item)
            item.setData(Qt.ItemDataRole.UserRole, {"type": "main"})
            self.nav_list.addItem(item)
            if main_item == "Sensors":
                for sub in ["Live Data", "Sensor Health", "Location Map"]:
                    sub_item = QListWidgetItem(f"   ↳ {sub}")
                    sub_item.setData(Qt.ItemDataRole.UserRole, {"type": "sub", "parent": main_item, "name": sub})
                    sub_item.setHidden(True)
                    self.nav_list.addItem(sub_item)

        self.nav_list.currentRowChanged.connect(self._on_nav_change)
        self.nav_list.itemClicked.connect(self._on_nav_click)

        # ───────────────────────────────
        # ALERT SERVICE + PANEL
        # ───────────────────────────────
        ws_url = os.getenv("ALERTS_WS", "ws://alerts-gateway:8000/ws/alerts")
        self.alert_service = AlertService(ws_url, api)
        self.alert_service.alertsUpdated.connect(self.update_alert_badge)
        self.alert_service.alertAdded.connect(lambda _: self.update_alert_badge())

        self.alerts_panel = AlertsPanel(self.alert_service)
        self.alerts_panel.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.alerts_panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.alerts_panel.setStyleSheet("""
            QWidget {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 10px;
            }
        """)
        self.alerts_panel.hide()
        self.alert_button.clicked.connect(self.toggle_alert_panel)

        # ───────────────────────────────
        # CENTRAL STACKED VIEWS
        # ───────────────────────────────
        self.home = HomeView(api, self.alert_service, self)
        self.sensors_view = SensorsView(api, self)
        self.notification_view = NotificationView(self)
        self.fruits_view = FruitsView(api, self)
        self.ground_view = GroundView(api, self)
        self.auth_status = AuthStatusView(api, self)

        self.sensors_status_summary = SensorsStatusSummary(api, self)
        self.sensors_health = SensorsView(api, self)
        self.sensors_main = SensorsMainView(api, self)
        print("[DEBUG] Creating IrrigationView...")
        try:
            self.irrigation_view = IrrigationView(api, self)
            print("[DEBUG] IrrigationView created successfully")
        except Exception as e:
            print(f"[ERROR] Failed to create IrrigationView: {e}")
            import traceback
            traceback.print_exc()
            self.irrigation_view = QWidget()  # Fallback empty widget

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.views = {
            "Home": self.home,
            "Sensors": self.sensors_view,
            "Sensors - Live Data": self.sensors_status_summary,
            "Sensors - Sensor Health": self.sensors_health,
            "Sensors - Location Map": self.sensors_main,
            "Notifications": self.notification_view,
            "Fruits": self.fruits_view,
            "Ground Image": self.ground_view,
            "Irrigation": self.irrigation_view,
            "Auth": self.auth_status
        }

        for view in self.views.values():
            self.stack.addWidget(view)
        self.stack.setCurrentWidget(self.home)
        self.history = []

        # ───────────────────────────────
        # STATUS BAR
        # ───────────────────────────────
        sb = QStatusBar(self)
        sb.setStyleSheet("QStatusBar { background-color: #f3f4f6; color: #374151; font-size: 10.5pt; }")
        self.setStatusBar(sb)
        sb.showMessage("Ready")

    # ───────────────────────────────
    # ALERT BADGE
    # ───────────────────────────────
    def update_alert_badge(self):
        unacked = sum(1 for a in self.alert_service.alerts if not a.get("ack", False))
        if unacked > 0:
            self.alert_badge.setText(str(unacked))
            self.alert_badge.show()
        else:
            self.alert_badge.hide()

    def toggle_alert_panel(self):
        if self.alerts_panel.isVisible():
            self.alerts_panel.hide()
            return

        panel_width, panel_height = 420, 540
        self.alerts_panel.resize(panel_width, panel_height)
        rect = self.alert_button.geometry()
        bottom_left = self.alert_button.mapToGlobal(rect.bottomLeft())
        bottom_right = self.alert_button.mapToGlobal(rect.bottomRight())
        center_x = (bottom_left.x() + bottom_right.x()) // 2 - (panel_width // 2)
        pos_y = bottom_left.y() + 8
        self.alerts_panel.move(center_x, pos_y)
        self.alerts_panel.show()
        self.alerts_panel.raise_()

        if hasattr(self.alert_service, "mark_all_acknowledged"):
            self.alert_service.mark_all_acknowledged()
        self.update_alert_badge()

    # ───────────────────────────────
    # NAVIGATION
    # ───────────────────────────────
    def _on_nav_change(self, row: int) -> None:
        name = self.nav_list.item(row).text().strip()
        print(f"[DEBUG] _on_nav_change: row={row}, name='{name}'")
        print(f"[DEBUG] Available views: {list(self.views.keys())}")
        if name in self.views:
            print(f"[DEBUG] Navigating to '{name}'")
            self.navigate_to(self.views[name])
        else:
            print(f"[DEBUG] Section '{name}' not found in views")
            self.statusBar().showMessage(f"Section '{name}' not implemented yet.")

    def _on_nav_click(self, item):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data and data.get("type") == "main":
            parent = item.text()
            expanded = False
            for i in range(self.nav_list.count()):
                sub_item = self.nav_list.item(i)
                sub_data = sub_item.data(Qt.ItemDataRole.UserRole)
                if sub_data and sub_data.get("type") == "sub" and sub_data.get("parent") == parent:
                    expanded = sub_item.isHidden()
                    break
            for i in range(self.nav_list.count()):
                sub_item = self.nav_list.item(i)
                sub_data = sub_item.data(Qt.ItemDataRole.UserRole)
                if sub_data and sub_data.get("type") == "sub" and sub_data.get("parent") == parent:
                    sub_item.setHidden(not expanded)
        elif data and data.get("type") == "sub":
            parent = data.get("parent")
            sub_name = data.get("name")
            key = f"{parent} - {sub_name}"
            if key in self.views:
                self.stack.setCurrentWidget(self.views[key])

    def navigate_to(self, widget):
        print(f"[DEBUG] navigate_to called with widget: {widget.__class__.__name__}")
        current = self.stack.currentWidget()
        if current not in self.history:
            self.history.append(current)
        print(f"[DEBUG] Setting current widget to: {widget.__class__.__name__}")
        self.stack.setCurrentWidget(widget)
        print(f"[DEBUG] Current widget is now: {self.stack.currentWidget().__class__.__name__}")

    def go_back(self):
        if self.history:
            last = self.history.pop()
            self.stack.setCurrentWidget(last)
        else:
            self.statusBar().showMessage("No previous view to go back to.")

    def _logout(self) -> None:
        self.statusBar().showMessage("Logged out (demo)")
        self.logoutRequested.emit()