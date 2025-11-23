from PyQt6.QtWidgets import QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QLabel, QHeaderView
from PyQt6.QtCore import Qt

class HistoryPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setFixedWidth(400)
        layout = QVBoxLayout(self)
        self.title = QLabel("Sprinkler History")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Timestamp','Device','Decision','Confidence','Dry Ratio','Image'])
        # self.table.horizontalHeader().setSectionResizeMode(QTableWidget.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet('alternate-background-color: #f9fafb; background: white;')
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)

    def show_history(self, records):
        self.table.setRowCount(0)
        for row in records:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r,0, QTableWidgetItem(str(row['ts'])))
            self.table.setItem(r,1, QTableWidgetItem(row['device_id']))
            dec_item = QTableWidgetItem(row['decision'])
            self.table.setItem(r,2, dec_item)
            self.table.setItem(r,3, QTableWidgetItem(f"{row['confidence']:.2f}"))
            self.table.setItem(r,4, QTableWidgetItem(f"{row['dry_ratio']:.2f}"))
            self.table.setItem(r,5, QTableWidgetItem("View Image"))
