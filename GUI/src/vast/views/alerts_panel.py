# views/alerts_panel.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QScrollArea, QFrame, QHBoxLayout
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from datetime import datetime, timezone
import re


# ────────────────────────────────────────────────
# Helper: parse timestamps from DB or realtime
# ────────────────────────────────────────────────
def _parse_time(value: str):
    """Safely parse a timestamp from DB or Alertmanager format."""
    if not value:
        return None

    v = value.strip().replace("Z", "+00:00")

    # Try ISO format first
    try:
        return datetime.fromisoformat(v)
    except Exception:
        pass

    # Try common fallback formats (Postgres or plain)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(v.split("+")[0], fmt)
        except Exception:
            continue
    return None


# ────────────────────────────────────────────────
# AlertItem Widget
# ────────────────────────────────────────────────
class AlertItem(QFrame):
    """Compact alert box with one-line layout that expands for longer text."""

    def __init__(self, alert):
        super().__init__()
        self.alert = alert
        self._build_ui()

    def _build_ui(self):
        color = "#FFC107"  # default amber tone

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
        summary = re.sub(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\+\d{2}:\d{2}|Z)?",
            "",
            summary
        ).strip()

        # --- Parse and format time ---
        start_raw = (
            self.alert.get("startsAt")
            or self.alert.get("started_at")
            or self.alert.get("startedAt")
        )
        dt = _parse_time(start_raw)
        time_str = dt.strftime("%Y-%m-%d %H:%M") if dt else "–"

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

    # ────────────────────────────────────────────────
    # Mark alert as resolved
    # ────────────────────────────────────────────────
    def mark_resolved(self, ended_at):
        """Change color and show duration when resolved."""
        try:
            start_str = (
                self.alert.get("startsAt")
                or self.alert.get("started_at")
                or self.alert.get("startedAt")
            )
            end_str = ended_at or self.alert.get("endedAt") or self.alert.get("ended_at")
            start = _parse_time(start_str)
            end = _parse_time(end_str)

            if start and end:
                dur = end - start
                mins = int(dur.total_seconds() // 60)
                secs = int(dur.total_seconds() % 60)
                duration = f"{mins}m {secs}s"
            else:
                duration = ""
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


# ────────────────────────────────────────────────
# AlertsPanel Widget
# ────────────────────────────────────────────────
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

    # ────────────────────────────────────────────────
    # Populate panel
    # ────────────────────────────────────────────────
    def _populate(self, alerts):
        # Remove all existing widgets
        for i in reversed(range(self.vbox.count())):
            widget = self.vbox.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self.items.clear()

        # Add in reverse chronological order
        for a in reversed(alerts):
            self._add_alert(a)

    # ────────────────────────────────────────────────
    # Add single alert
    # ────────────────────────────────────────────────
    def _add_alert(self, alert):
        alert_id = alert.get("alert_id")
        if not alert_id or alert_id in self.items:
            return

        item = AlertItem(alert)
        self.vbox.insertWidget(0, item)
        self.items[alert_id] = item

        # ✅ If alert is resolved already, mark as resolved
        ended_at = alert.get("ended_at") or alert.get("endedAt")
        if ended_at:
            item.mark_resolved(ended_at)

    # ────────────────────────────────────────────────
    # Mark resolved by ID
    # ────────────────────────────────────────────────
    def _mark_resolved(self, alert_id):
        item = self.items.get(alert_id)
        if item:
            for a in self.alert_service.alerts:
                if a.get("alert_id") == alert_id:
                    ended_at = a.get("endedAt") or a.get("ended_at")
                    break
            else:
                ended_at = datetime.now(timezone.utc).isoformat()
            item.mark_resolved(ended_at)
