# views/alerts_panel.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from datetime import datetime, timezone
import re
from datetime import datetime

class AlertItem(QFrame):
    """Compact alert box with one-line layout that expands for longer text."""

    def __init__(self, alert):
        super().__init__()
        self.alert = alert
        self._build_ui()

    def _build_ui(self):
        sev = int(self.alert.get("severity", 1))
        # Updated color map — no purple, cleaner tones
        color_map = {
            1: "#4CAF50",  # green
            2: "#FFC107",  # amber
            3: "#FF9800",  # orange
            4: "#F44336",  # red
            5: "#E53935",  # darker red
            6: "#1976D2",  # blue instead of purple
        }
        color = color_map.get(sev, "#2196F3")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(10)

        # Left colored bar
        bar = QFrame()
        bar.setFixedWidth(5)
        bar.setStyleSheet(f"background-color: {color}; border-radius: 2px;")
        layout.addWidget(bar)

        # Alert details
        alert_type = self.alert.get("alert_type", "Unknown")
        device = self.alert.get("device_id", "")
        summary = self.alert.get("summary", "No summary")
        # Remove ISO timestamps from summary text
        summary = re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+\d{2}:\d{2}|Z)?", "", summary).strip()

        # --- Format the time separately from startsAt ---
        start = self.alert.get("startsAt", "")
        try:
            if start:
                cleaned = re.sub(r"(\.\d+)?(\+|\-)\d{2}:\d{2}$", "", start)  # remove milliseconds/timezone
                cleaned = cleaned.replace("T", " ")
                dt = datetime.fromisoformat(cleaned)
                time_str = dt.strftime("%Y-%m-%d %H:%M")  # ✅ clean date + hour
            else:
                time_str = "–"
        except Exception:
            time_str = "–"


        # --- Alert text ---
        is_unack = not self.alert.get("ack", False)
        font_weight = "font-weight:600;" if is_unack else "font-weight:normal;"
        text = QLabel(
            f"<b style='color:{color};{font_weight}'>{alert_type}</b> "
            f"on <i>{device}</i> — {summary} "
            f"<span style='color:#666;font-size:9pt;'>🕒 {time_str}</span>"
        )

        text.setWordWrap(True)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.setFont(QFont("Segoe UI", 9))
        layout.addWidget(text, 1)

        # Right status label
        self.status_label = QLabel("ACTIVE")
        self.status_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.status_label.setStyleSheet(f"color:{color};")
        layout.addWidget(self.status_label, alignment=Qt.AlignmentFlag.AlignRight)

        # Allow box to expand vertically if needed
        self.setMinimumHeight(65)
        self.setMaximumHeight(130)

        # Style
        self.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #ddd;
                border-radius: 8px;
            }
        """)

    def mark_resolved(self, ended_at):
        """Change color and show duration when resolved."""
        try:
            start = datetime.fromisoformat(self.alert["startsAt"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
            dur = end - start
            mins = int(dur.total_seconds() // 60)
            secs = int(dur.total_seconds() % 60)
            duration = f"{mins}m {secs}s"
        except Exception:
            duration = ""

        self.status_label.setText(f"✓ {duration}")
        self.status_label.setStyleSheet("color:#2E7D32; font-weight:bold;")
        self.setStyleSheet("""
            QFrame {
                background-color: #f6fff6;
                border: 1px solid #b8e5b8;
                border-radius: 8px;
            }
        """)


class AlertsPanel(QWidget):
    """Floating list of alert boxes (like a modern notification dropdown)."""

    def __init__(self, alert_service):
        super().__init__()
        self.alert_service = alert_service
        self.items = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                width: 8px;
                background: #f0f0f0;
                margin: 2px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #bbb;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #999;
            }
        """)
        layout.addWidget(scroll)

        # Inner container
        container = QWidget()
        self.vbox = QVBoxLayout(container)
        self.vbox.setContentsMargins(6, 6, 6, 6)
        self.vbox.setSpacing(8)
        self.vbox.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(container)

        # Connect signals
        self.alert_service.alertsUpdated.connect(self._populate)
        self.alert_service.alertAdded.connect(self._add_alert)
        self.alert_service.alertRemoved.connect(self._mark_resolved)

        # Load initial alerts
        QTimer.singleShot(500, self.alert_service.load_initial)

    def _populate(self, alerts):
        for a in reversed(alerts):
            self._add_alert(a)

    def _add_alert(self, alert):
        if alert["alert_id"] in self.items:
            return
        item = AlertItem(alert)
        self.vbox.insertWidget(0, item)
        self.items[alert["alert_id"]] = item

    def _mark_resolved(self, alert_id):
        item = self.items.get(alert_id)
        if item:
            for a in self.alert_service.alerts:
                if a.get("alert_id") == alert_id:
                    ended_at = a.get("endedAt")
                    break
            else:
                ended_at = datetime.now(timezone.utc).isoformat()
            item.mark_resolved(ended_at)
