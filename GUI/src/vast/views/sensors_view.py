from PyQt6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem
from dashboard_api import DashboardApi


class SensorsView(QWidget):
    def __init__(self, api: DashboardApi, parent=None):
        super().__init__(parent)
        self.api = api

        layout = QVBoxLayout(self)
        title = QLabel("Sensor Types")
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)

        self.table = QTableWidget()
        layout.addWidget(self.table)

        refresh_btn = QPushButton("Load Sensor Types")
        refresh_btn.clicked.connect(self.load_sensors)
        layout.addWidget(refresh_btn)

        layout.addStretch()

    def load_sensors(self):
        try:
            data = self.api.http.get(f"{self.api.base}/api/files").json()
        except Exception as e:
            print(f"[SensorsView] API error: {e}")
            data = []

        if not data:
            self.table.setRowCount(0)
            self.table.setColumnCount(1)
            self.table.setHorizontalHeaderLabels(["No data"])
            return

        keys = list(data[0].keys())
        self.table.setColumnCount(len(keys))
        self.table.setHorizontalHeaderLabels(keys)
        self.table.setRowCount(len(data))

        for r, row in enumerate(data):
            for c, key in enumerate(keys):
                self.table.setItem(r, c, QTableWidgetItem(str(row[key])))
