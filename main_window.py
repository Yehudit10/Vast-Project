from __future__ import annotations
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QMainWindow, QDockWidget, QListWidget, QListWidgetItem, QStatusBar, QAction
from PyQt5.QtGui import QIcon
from home_view import HomeView
from dashboard_api import DashboardApi

class MainWindow(QMainWindow):
    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        print("[MainWindow] init start", flush=True)
        self.setWindowTitle("VAST – Dashboard")
        self.resize(1100, 700)

        # Menu
        print("[MainWindow] building menu...", flush=True)
        file_menu = self.menuBar().addMenu("&File")
        self.logout_action = QAction(QIcon(), "Log out", self)
        self.logout_action.triggered.connect(self._logout)
        file_menu.addAction(self.logout_action)
        print("[MainWindow] menu ready", flush=True)

        # Dock nav
        print("[MainWindow] building nav dock...", flush=True)
        self.nav_dock = QDockWidget("Navigation", self)
        self.nav_dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.nav_dock)

        self.nav_list = QListWidget(self.nav_dock)
        self.nav_dock.setWidget(self.nav_list)
        for name in ["Home", "Sensors", "Sound", "Ground Image", "Aerial Image", "Fruits", "Security", "Settings"]:
            QListWidgetItem(name, self.nav_list)
        self.nav_list.setCurrentRow(0)
        self.nav_list.currentRowChanged.connect(self._on_nav_change)
        print("[MainWindow] nav dock ready", flush=True)

        # Central Home
        print("[MainWindow] creating HomeView...", flush=True)
        self.home = HomeView(api, self)
        connections = [
            ("openSensorsRequested",    lambda: self._select_nav("Sensors")),
            ("openAlertsRequested",     lambda: self.statusBar().showMessage("Alerts not implemented yet.")),
            ("openProcessingRequested", lambda: self.statusBar().showMessage("Processing not implemented yet.")),
            ("openPredictionsRequested",lambda: self.statusBar().showMessage("Predictions not implemented yet.")),
            ("openSettingsRequested",   lambda: self._select_nav("Settings")),
        ]

        for attr, slot in connections:
            sig = getattr(self.home, attr, None)
            if sig is not None:
                sig.connect(slot)

        self.setCentralWidget(self.home)
        print("[MainWindow] HomeView set", flush=True)

        # Status bar
        print("[MainWindow] adding status bar...", flush=True)
        sb = QStatusBar(self)
        self.setStatusBar(sb)
        sb.showMessage("Ready")
        print("[MainWindow] status bar ready", flush=True)

        # Style
        print("[MainWindow] applying style...", flush=True)
        self.setStyleSheet("""
        QMainWindow { background: #FAFAFA; }
        QDockWidget { background: #FFFFFF; }
        QListWidget::item { padding: 8px 6px; }
        QListWidget::item:selected { background: #E0E0E0; }
        """)
        print("[MainWindow] init done", flush=True)

    def _on_nav_change(self, row: int) -> None:
        msg = "Home" if row == 0 else "This section is not implemented yet."
        self.statusBar().showMessage(msg)

    def _select_nav(self, name: str) -> None:
    # Select a nav item by its text, if it exists
        items = [self.nav_list.item(i).text() for i in range(self.nav_list.count())]
        if name in items:
            idx = items.index(name)
            self.nav_list.setCurrentRow(idx)
        else:
            self.statusBar().showMessage(f"Section '{name}' not found.")


    def _logout(self) -> None:
        self.statusBar().showMessage("Logged out (demo)")

