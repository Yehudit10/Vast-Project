from __future__ import annotations
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QMainWindow, QDockWidget, QListWidget, QListWidgetItem, QStatusBar, QStackedWidget
)
from PyQt6.QtGui import QAction, QIcon

from home_view import HomeView
from views.sensors_view import SensorsView
from views.security.incident_player_vlc import IncidentPlayerVLC
from dashboard_api import DashboardApi


class MainWindow(QMainWindow):
    logoutRequested = pyqtSignal()

    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        print("[MainWindow] init start", flush=True)
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

        # Toolbar
        toolbar = self.addToolBar("Main Toolbar")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(24, 24))
        toolbar.addAction(self.back_action)
        toolbar.addAction(self.logout_action)

        # ---------- Dock navigation ----------
        self.nav_dock = QDockWidget("Navigation", self)
        self.nav_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.nav_dock)

        self.nav_list = QListWidget(self.nav_dock)
        self.nav_dock.setWidget(self.nav_list)
        for name in [
            "Home", "Sensors", "Sound", "Ground Image",
            "Aerial Image", "Fruits", "Security", "Settings"
        ]:
            QListWidgetItem(name, self.nav_list)
        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._on_nav_change)

        # ---------- Views ----------
        self.home = HomeView(api, self)
        self.sensors_view = SensorsView(api, self)
        # self.security_view = IncidentPlayerVLC(api, self)

        # Stack for switching between views without destroying them
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.views = {
            "Home": self.home,
            "Sensors": self.sensors_view,
            # "Security": self.security_view,
        }
        for view in self.views.values():
            self.stack.addWidget(view)
        self.stack.setCurrentWidget(self.home)

        # ---------- History ----------
        self.history: list = []

        # ---------- Connect signals ----------
        connections = [
            ("openSensorsRequested", lambda: self._select_nav("Sensors")),
            ("openAlertsRequested", lambda: self.statusBar().showMessage("Alerts not implemented yet.")),
            ("openProcessingRequested", lambda: self.statusBar().showMessage("Processing not implemented yet.")),
            ("openPredictionsRequested", lambda: self.statusBar().showMessage("Predictions not implemented yet.")),
            ("openSettingsRequested", lambda: self._select_nav("Settings")),
        ]
        for attr, slot in connections:
            sig = getattr(self.home, attr, None)
            if sig is not None:
                sig.connect(slot)

        # ---------- Status bar ----------
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        sb.showMessage("Ready")

        # ---------- Style ----------
        self.setStyleSheet("""
        QMainWindow { background: #FAFAFA; }
        QDockWidget { background: #FFFFFF; }
        QListWidget::item { padding: 8px 6px; }
        QListWidget::item:selected { background: #E0E0E0; }
        """)

        print("[MainWindow] init done", flush=True)

    # ---------- Navigation ----------
    def _on_nav_change(self, row: int) -> None:
        name = self.nav_list.item(row).text()
        if name in self.views:
            self.navigate_to(self.views[name])
        else:
            self.statusBar().showMessage(f"Section '{name}' not implemented yet.")

    def _select_nav(self, name: str) -> None:
        items = [self.nav_list.item(i).text() for i in range(self.nav_list.count())]
        if name in items:
            idx = items.index(name)
            self.nav_list.setCurrentRow(idx)
        else:
            self.statusBar().showMessage(f"Section '{name}' not found.")

    # ---------- Back Navigation ----------
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

    # ---------- Logout ----------
    def _logout(self) -> None:
        self.statusBar().showMessage("Logged out (demo)")
        self.logoutRequested.emit()
