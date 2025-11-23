from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QVBoxLayout, QFrame
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from datetime import datetime

class DashboardBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Clean minimalistic style: no background, only bottom border
        self.setStyleSheet("""
            QWidget {
                background: transparent;
                border-bottom: 1px solid #e5e7eb;
            }
            QLabel.title {
                color: #6b7280;
                font-size: 10pt;
                font-weight: 500;
            }
            QLabel.value {
                color: #111827;
                font-size: 18pt;
                font-weight: 600;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(32)

        # Helper: metric block
        def metric(title_text, value_text, big=True):
            container = QWidget()
            v = QVBoxLayout(container)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)

            title = QLabel(title_text)
            title.setProperty("class", "title")

            value = QLabel(value_text)
            value.setProperty("class", "value" if big else "title")

            v.addWidget(title)
            v.addWidget(value)
            return container, value

        # Metric 1
        block, self.active_value = metric("Active Sprinklers", "0")
        layout.addWidget(block)

        layout.addWidget(self._separator())

        # Metric 2
        block, self.area_value = metric("Irrigated Area", "0%")
        layout.addWidget(block)

        layout.addWidget(self._separator())

        # Metric 3
        block, self.time_value = metric("Last Update", "--", big=False)
        layout.addWidget(block)

        layout.addStretch()

        # Status container (clean version)
        self.status_container = QWidget()
        s = QHBoxLayout(self.status_container)
        s.setContentsMargins(0, 0, 0, 0)
        s.setSpacing(6)

        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: #dc2626; font-size: 12px;")

        self.status_text = QLabel("Disconnected")
        self.status_text.setFont(QFont('Segoe UI', 10))
        self.status_text.setStyleSheet("color: #dc2626; font-weight: 600;")

        s.addWidget(self.status_indicator)
        s.addWidget(self.status_text)
        layout.addWidget(self.status_container)

    def _separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #e5e7eb;")
        sep.setFixedWidth(1)
        return sep

    def update_status(self, active_count, area_percent, last_update, healthy):
        self.active_value.setText(str(active_count))
        self.area_value.setText(f"{area_percent:.1f}%")

        if last_update:
            try:
                if isinstance(last_update, str):
                    last_dt = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
                else:
                    last_dt = last_update

                now = datetime.now(last_dt.tzinfo) if last_dt.tzinfo else datetime.now()
                delta = now - last_dt
                seconds = int(delta.total_seconds())

                if seconds < 60:
                    t = f"{seconds}s ago"
                elif seconds < 3600:
                    t = f"{seconds // 60}m ago"
                else:
                    t = f"{seconds // 3600}h ago"

                self.time_value.setText(t)
            except:
                self.time_value.setText("--")
        else:
            self.time_value.setText("--")

        # Status indicator styling
        if healthy:
            self.status_indicator.setStyleSheet("color: #16a34a; font-size: 12px;")
            self.status_text.setText("Connected")
            self.status_text.setStyleSheet("color: #16a34a; font-weight: 600;")
        else:
            self.status_indicator.setStyleSheet("color: #dc2626; font-size: 12px;")
            self.status_text.setText("Disconnected")
            self.status_text.setStyleSheet("color: #dc2626; font-weight: 600;")
