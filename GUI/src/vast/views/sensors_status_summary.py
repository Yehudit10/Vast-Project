from math import ceil
from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QScrollArea
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPen, QPainterPath

# ============================================================
# 🎨 CIRCLE ICON (Stroke icons drawn manually)
# ============================================================
class CircleIcon(QWidget):
    def __init__(self, icon_type: str, color: str, size: int = 58):
        super().__init__()
        self.icon_type = icon_type
        self.color = color
        self.size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background circle
        bg = QColor(self._lighten(self.color, 0.70))
        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self.size, self.size)

        # Icon stroke
        painter.setPen(QPen(QColor(self._dark(self.color)), 3,
                            Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))

        # Build path
        path = self._icon_path()
        scale = self.size / 58
        painter.scale(scale, scale)
        painter.drawPath(path)

    # ---------------- Icon shapes ----------------
    def _icon_path(self):
        p = QPainterPath()

        if self.icon_type == "people":
            p.addEllipse(14, 14, 12, 12)
            p.addEllipse(32, 14, 12, 12)
            p.moveTo(10, 40)
            p.cubicTo(18, 30, 28, 30, 36, 40)
            p.moveTo(22, 40)
            p.cubicTo(30, 30, 40, 30, 48, 40)

        elif self.icon_type == "bell":
            p.moveTo(29, 12)
            p.arcTo(19, 12, 20, 20, 0, 180)
            p.lineTo(19, 38)
            p.lineTo(39, 38)
            p.lineTo(39, 32)
            p.addEllipse(26, 44, 6, 6)

        elif self.icon_type == "graph":
            p.moveTo(12, 40)
            p.lineTo(24, 28)
            p.lineTo(32, 34)
            p.lineTo(46, 20)

        elif self.icon_type == "bolt":
            p.moveTo(28, 12)
            p.lineTo(20, 30)
            p.lineTo(30, 30)
            p.lineTo(22, 48)
            p.lineTo(40, 26)
            p.lineTo(30, 26)
            p.closeSubpath()

        return p

    # ---------------- Color helpers ----------------
    def _lighten(self, hex_color, factor):
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
        return f"#{r:02X}{g:02X}{b:02X}"

    def _dark(self, hex_color):
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = int(r * 0.35)
        g = int(g * 0.35)
        b = int(b * 0.35)
        return f"#{r:02X}{g:02X}{b:02X}"


# ============================================================
# 🔵 RING INDICATOR
# ============================================================
class RingIndicator(QWidget):
    def __init__(self, label, value, color="#10B981", max_value=100, size=200):
        super().__init__()
        self.label = label
        self.value = value
        self.color = color
        self.max_value = max_value
        self.size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()

        radius = int(min(rect.width(), rect.height()) / 2 - 15)
        center = rect.center()

        # Background circle
        painter.setPen(QPen(QColor("#E5E7EB"), 16))
        painter.drawEllipse(center, radius, radius)

        # Colored ring
        pen = QPen(QColor(self.color), 16)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        angle_span = int(360 * (self.value / self.max_value))
        painter.drawArc(rect.adjusted(15, 15, -15, -15), 90 * 16, -angle_span * 16)

        # Text
        painter.setPen(QColor("#1E293B"))
        painter.setFont(QFont("Segoe UI", 30, QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{ceil(self.value)}%")
# ============================================================
# 🌿 MAIN DASHBOARD – BUILD UI
# ============================================================
class SensorsStatusSummary(QWidget):
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self._events_cache = []
        self._last_event_id = 0
        self._first_load = True

        self._build_ui()
        self.refresh_data()

        # Auto refresh every 30 sec
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(30000)

    # ============================================================
    # 🧱 BUILD UI
    # ============================================================
    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)

        # ------------------------------------------------------------
        # Header
        # ------------------------------------------------------------
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        icon_lbl = QLabel("🩺")
        icon_lbl.setFont(QFont("Segoe UI Emoji", 28))
        header_row.addWidget(icon_lbl)

        title = QLabel("Sensors Health Overview")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet("color:#0F172A; letter-spacing: -0.5px;")
        header_row.addWidget(title)

        header_row.addStretch()

        self.status_badge = QLabel("Live • Updated just now")
        self.status_badge.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        self.status_badge.setStyleSheet("""
            QLabel {
                color: #047857;
                background-color: #D1FAE5;
                border: 1px solid #A7F3D0;
                border-radius: 12px;
                padding: 8px 16px;
            }
        """)
        header_row.addWidget(self.status_badge)
        main_layout.addLayout(header_row)

        # ------------------------------------------------------------
        # Status cards row
        # ------------------------------------------------------------
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)

        self.active_card = self._create_status_card("Active Sensors", "0", "#22C55E", "people")
        self.inactive_card = self._create_status_card("Inactive (No KeepAlive)", "0", "#F97316", "bell")
        self.outofrange_card = self._create_status_card("Out of Range", "0", "#EF4444", "graph")
        self.corrupted_card = self._create_status_card("Corrupted", "0", "#8B5CF6", "bolt")

        cards_row.addWidget(self.active_card)
        cards_row.addWidget(self.inactive_card)
        cards_row.addWidget(self.outofrange_card)
        cards_row.addWidget(self.corrupted_card)

        main_layout.addLayout(cards_row)

        # ------------------------------------------------------------
        # LOWER SECTION
        # ------------------------------------------------------------
        lower_row = QHBoxLayout()
        lower_row.setSpacing(24)

        # === LEFT: ring ===
        left_frame = QFrame()
        left_frame.setStyleSheet("background:white; border-radius:16px;")
        left_l = QVBoxLayout(left_frame)
        left_l.setContentsMargins(30, 30, 30, 30)
        left_l.setSpacing(10)

        ring_title = QLabel("System Health")
        ring_title.setFont(QFont("Segoe UI", 16))
        ring_title.setStyleSheet("color:#1E293B;")
        left_l.addWidget(ring_title)

        self.health_ring = RingIndicator("Health", 0, "#10B981", 100, 220)
        left_l.addWidget(self.health_ring, alignment=Qt.AlignmentFlag.AlignCenter)

        self.ring_bottom = QLabel("Loading...")
        self.ring_bottom.setFont(QFont("Segoe UI", 11))
        self.ring_bottom.setStyleSheet("color: #94A3B8; margin-top: 6px;")
        self.ring_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_l.addWidget(self.ring_bottom)

        lower_row.addWidget(left_frame, 1)

        # === RIGHT: Inactive table ===
        right_frame = QFrame()
        right_frame.setStyleSheet("background:white; border-radius:16px;")
        right_l = QVBoxLayout(right_frame)
        right_l.setContentsMargins(30, 30, 30, 30)
        right_l.setSpacing(10)

        table_title = QLabel("Inactive Sensors (Missing KeepAlive)")
        table_title.setFont(QFont("Segoe UI", 16))
        table_title.setStyleSheet("color:#1E293B; margin-bottom:10px;")
        right_l.addWidget(table_title)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Sensor Type", "Last Seen"])

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 60)

        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                font-family: 'Segoe UI';
                font-size: 13px;
                border: none;
                border-radius: 12px;
                gridline-color: #E5E7EB;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #64748B;
                font-weight: 600;
                padding: 10px;
                border: none;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)

        right_l.addWidget(self.table)
        lower_row.addWidget(right_frame, 2)

        main_layout.addLayout(lower_row)

        self.setStyleSheet("background-color:#F8FAFC;")

        self.setLayout(main_layout)

    # ============================================================
    # CARD WIDGET
    # ============================================================
    def _create_status_card(self, title, value, color, icon_type):
        frame = QFrame()
        frame.setStyleSheet("background:white; border-radius:16px; padding:4px;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Icon drawn via QPainterPath
        icon = CircleIcon(icon_type, color)
        layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)

        # Number
        val_label = QLabel(value)
        val_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        val_label.setStyleSheet("color:#1E293B;")
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame.value_label = val_label
        layout.addWidget(val_label)

        # Title
        title_lbl = QLabel(title)
        title_lbl.setFont(QFont("Segoe UI", 11))
        title_lbl.setStyleSheet("color:#64748B;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)

        return frame
    # ============================================================
    # 🔄 REFRESH DATA (MAIN LOGIC)
    # ============================================================
    def refresh_data(self):
        try:
            print("\n[SensorsStatusSummary] ===== REFRESH DATA START =====")

            # === Load sensors ===
            res_sensors = self.api.http.get(f"{self.api.base}/api/tables/devices_sensor")
            sensors = res_sensors.json().get("rows", [])
            print(f"[SensorsStatusSummary] Loaded {len(sensors)} sensors")

            # === Load new events incrementally ===
            if self._first_load:
                print("[SensorsStatusSummary] Initial load - fetching events...")
                res_events = self.api.http.get(
                    f"{self.api.base}/api/tables/event_logs_sensors?limit=500&order_by=id&order_dir=desc"
                )
                self._events_cache = res_events.json().get("rows", [])
                if self._events_cache:
                    self._last_event_id = max(e.get("id", 0) for e in self._events_cache)
                self._first_load = False

            else:
                print(f"[SensorsStatusSummary] Fetching new events after ID={self._last_event_id}")
                res_events = self.api.http.get(
                    f"{self.api.base}/api/tables/event_logs_sensors?limit=500&order_by=id&order_dir=asc"
                )
                new_events = [
                    e for e in res_events.json().get("rows", [])
                    if e.get("id", 0) > self._last_event_id
                ]

                if new_events:
                    print(f"[SensorsStatusSummary] Found {len(new_events)} new events")
                    self._events_cache.extend(new_events)
                    self._last_event_id = max(
                        self._last_event_id,
                        max(e.get("id", 0) for e in new_events)
                    )
                    self._events_cache = self._events_cache[-5000:]  # Cap
                else:
                    print("[SensorsStatusSummary] No new events")

            events = self._events_cache
            print(f"[SensorsStatusSummary] Total cached events: {len(events)}")

            # === Analyze events ===
            latest_issues = self._get_latest_open_issues(events)

            inactive = [e for e in latest_issues if e.get("issue_type") == "missing_keepalive"]
            outofrange = [e for e in latest_issues if e.get("issue_type") == "out_of_range"]
            corrupted = [e for e in latest_issues if e.get("issue_type") in ["corrupted", "stuck_sensor"]]

            print(f"[SensorsStatusSummary] Categorized:")
            print(f"  - Inactive: {len(inactive)}")
            print(f"  - Out of range: {len(outofrange)}")
            print(f"  - Corrupted: {len(corrupted)}")

            # Sensors with issues
            problematic_ids = {str(e.get("device_id")) for e in latest_issues if e.get("device_id")}
            total = len(sensors)
            active = [s for s in sensors if str(s.get("id")) not in problematic_ids]

            health = int((len(active) / total * 100)) if total else 0

            print(f"  Total sensors: {total}")
            print(f"  Active sensors: {len(active)}")
            print(f"  Health: {health}%")

            # === Update UI ===
            self.active_card.value_label.setText(str(len(active)))
            self.inactive_card.value_label.setText(str(len(inactive)))
            self.outofrange_card.value_label.setText(str(len(outofrange)))
            self.corrupted_card.value_label.setText(str(len(corrupted)))

            # Ring
            self.health_ring.value = health
            self.health_ring.update()
            self.ring_bottom.setText(f"{len(active)} active sensors of {total}")

            # Timestamp
            now = datetime.now(timezone.utc)
            self.status_badge.setText(f"Live • Updated at {now.strftime('%H:%M:%S')}")

            # Table
            self._update_inactive_table(inactive, sensors)

            print("[SensorsStatusSummary] ===== REFRESH DATA END =====\n")

        except Exception as e:
            print(f"[SensorsStatusSummary] ❌ ERROR refreshing data: {e}")
            import traceback
            traceback.print_exc()


    # ============================================================
    # 🔍 ANALYZE — find latest open issue per sensor
    # ============================================================
    def _get_latest_open_issues(self, events):
        issue_types = ["missing_keepalive", "out_of_range", "corrupted", "stuck_sensor"]

        last_events = {}

        for e in events:
            dev = e.get("device_id")
            itype = e.get("issue_type")
            if not dev or itype not in issue_types:
                continue

            key = (str(dev), itype)
            if key not in last_events or e.get("id", 0) > last_events[key].get("id", 0):
                last_events[key] = e

        # Choose highest-severity open issue per device
        priority = {"corrupted": 3, "stuck_sensor": 3, "out_of_range": 2, "missing_keepalive": 1}
        result = {}

        for (dev, itype), ev in last_events.items():
            if ev.get("end_ts") is None:  # Still open
                if dev not in result or priority[itype] > priority[result[dev]["issue_type"]]:
                    result[dev] = ev

        return list(result.values())


    # ============================================================
    # 📋 UPDATE TABLE (inactive sensors only)
    # ============================================================
    def _update_inactive_table(self, inactive_events, sensors):
        self.table.setRowCount(0)

        sensor_map = {str(s.get("id")): s for s in sensors}
        sorted_events = sorted(inactive_events, key=lambda e: int(e.get("device_id", 0)))

        for ev in sorted_events:
            dev_id = str(ev.get("device_id"))
            sensor = sensor_map.get(dev_id)
            if not sensor:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            last_seen = sensor.get("last_seen")
            try:
                dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except:
                time_str = "—"

            # ID
            id_item = QTableWidgetItem(dev_id)
            self.table.setItem(row, 0, id_item)

            # Type
            self.table.setItem(row, 1, QTableWidgetItem(sensor.get("sensor_type", "Unknown")))

            # Last seen
            ts_item = QTableWidgetItem(time_str)
            ts_item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            ts_item.setForeground(QColor("#DC2626"))
            self.table.setItem(row, 2, ts_item)
