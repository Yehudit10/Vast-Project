from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QTabWidget
from PyQt6.QtCore import Qt
from views.sensorsMapView import SensorsMapView
from views.sensorDetailsTab import SensorDetailsTab


class SensorsMainView(QWidget):
    """
    Main container for the sensors module.
    Contains two tabs:
    1. Map view (SensorsMapView)
    2. Sensor details (SensorDetailsTab)
    """
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("🌾 Sensors Dashboard")
        self.setMinimumSize(1100, 750)

        # --- Layout --- #
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # --- Header --- #
        title = QLabel("📡 Sensors Dashboard")
        title.setStyleSheet("""
            font-size:22px;
            font-weight:800;
            color:#0f172a;
            margin-bottom:4px;
        """)
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignLeft)

        # --- Tabs --- #
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                background: #f8fafc;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
                background: #e2e8f0;
                border-radius: 6px 6px 0 0;
                font-weight: 600;
                color: #0f172a;
            }
            QTabBar::tab:selected {
                background: #2563eb;
                color: white;
            }
        """)

        # --- Map tab --- #
        self.map_tab = SensorsMapView(api, self)
        self.tabs.addTab(self.map_tab, "🗺️ Map")

        # --- Details tab --- #
        self.details_tab = SensorDetailsTab(api, self)
        self.tabs.addTab(self.details_tab, "📊 Sensor Details")

        # Add tabs to layout
        layout.addWidget(self.tabs)

    # ==========================================================
    # === Navigation between tabs
    # ==========================================================
    def show_sensor_details(self, sensor_id: str):
        """
        Called by the map (via JS bridge) when user clicks 'view details' on a sensor.
        Loads the details tab and switches to it.
        """
        print(f"[SensorsMainView] Showing details for sensor: {sensor_id}")
        self.details_tab.load_sensor(sensor_id)
        self.tabs.setCurrentIndex(1)

    def back_to_map(self):
        """Switch back to the map tab."""
        print("[SensorsMainView] Returning to map tab")
        self.tabs.setCurrentIndex(0)
