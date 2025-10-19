from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QFont

class StatusCard(QWidget):
    openRequested = pyqtSignal()

    def __init__(self, title: str, value: str, description: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StatusCard")

        self.title_label = QLabel(title)
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        self.title_label.setFont(title_font)

        self.value_label = QLabel(value)
        value_font = QFont()
        value_font.setPointSize(22)
        value_font.setBold(True)
        self.value_label.setFont(value_font)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.desc_label = QLabel(description)
        desc_font = QFont()
        desc_font.setPointSize(9)
        self.desc_label.setFont(desc_font)
        self.desc_label.setStyleSheet("color: gray;")

        self.open_btn = QPushButton("Open")
        self.open_btn.clicked.connect(self.openRequested.emit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.desc_label)
        layout.addWidget(self.open_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.setStyleSheet("""
        #StatusCard {
            border: 1px solid #E0E0E0;
            border-radius: 12px;
            background: #FFFFFF;
        }
        """)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)

    def set_description(self, text: str) -> None:
        self.desc_label.setText(text)

