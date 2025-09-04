from __future__ import annotations
from PyQt5.QtWidgets import QFrame, QLabel, QPushButton, QHBoxLayout

class ErrorBanner(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("errorBanner")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setVisible(False)
        self._label = QLabel()
        self._label.setWordWrap(True)
        close_btn = QPushButton("×")
        close_btn.setFixedWidth(28)
        close_btn.clicked.connect(lambda: self.setVisible(False))
        lay = QHBoxLayout(self)
        lay.addWidget(self._label, 1)
        lay.addWidget(close_btn, 0)

    def show_message(self, text: str) -> None:
        self._label.setText(text)
        self.setVisible(True)
