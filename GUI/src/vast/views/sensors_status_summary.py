from math import ceil
from datetime import datetime, timezone
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QPainter, QPen


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

        # רקע טבעת אפור בהיר
        bg_pen = QPen(QColor("#E5E7EB"), 16)
        painter.setPen(bg_pen)
        painter.drawEllipse(center, radius, radius)

        # טבעת צבעונית
        pen = QPen(QColor(self.color), 16)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        angle_span = int(360 * (self.value / self.max_value))
        painter.drawArc(rect.adjusted(15, 15, -15, -15), 90 * 16, -angle_span * 16)

        # טקסט במרכז
        painter.setPen(QColor("#1E293B"))
        font = QFont("Segoe UI", 30, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{ceil(self.value)}%")
        painter.end()


# ============================================================
# 🌿 MAIN DASHBOARD
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

        # Auto-refresh every 30 seconds
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

        # HEADER
        header_row = QHBoxLayout()
        header_row.setSpacing(16)
        
        # Title with subtle styling
        title = QLabel("Sensors Health Overview")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        title.setStyleSheet("""
            QLabel {
                color: #0F172A;
                letter-spacing: -0.5px;
            }
        """)

        # Status badge with last update time
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

        header_row.addWidget(title)
        header_row.addStretch()
        header_row.addWidget(self.status_badge)
        main_layout.addLayout(header_row)

        # CARDS ROW
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)
        self.active_card = self._create_status_card("Active Sensors", "0", "#22C55E")
        self.inactive_card = self._create_status_card("Inactive (No KeepAlive)", "0", "#F97316")
        self.outofrange_card = self._create_status_card("Out of Range", "0", "#EF4444")
        self.corrupted_card = self._create_status_card("Corrupted", "0", "#8B5CF6")

        for c in [self.active_card, self.inactive_card, self.outofrange_card, self.corrupted_card]:
            cards_row.addWidget(c, 1)  # Equal stretch factor for all cards
        main_layout.addLayout(cards_row)

        # LOWER SECTION
        lower_row = QHBoxLayout()
        lower_row.setSpacing(24)

        # LEFT: Ring
        left_frame = QFrame()
        left_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 16px;
                padding: 4px;
            }
        """)
        left_layout = QVBoxLayout(left_frame)
        left_layout.setContentsMargins(30, 30, 30, 30)
        left_layout.setSpacing(10)

        ring_title = QLabel("System Health")
        ring_title.setFont(QFont("Segoe UI", 16))
        ring_title.setStyleSheet("color: #1E293B;")
        left_layout.addWidget(ring_title)

        self.health_ring = RingIndicator("Health", 0, "#10B981", 100, 220)
        left_layout.addWidget(self.health_ring, alignment=Qt.AlignmentFlag.AlignCenter)

        self.ring_bottom = QLabel("Loading...")
        self.ring_bottom.setFont(QFont("Segoe UI", 11))
        self.ring_bottom.setStyleSheet("color: #94A3B8; margin-top: 6px;")
        self.ring_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.ring_bottom)
        lower_row.addWidget(left_frame, 1)

        # RIGHT: Table
        right_frame = QFrame()
        right_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 16px;
                padding: 4px;
            }
        """)
        right_layout = QVBoxLayout(right_frame)
        right_layout.setContentsMargins(30, 30, 30, 30)

        table_title = QLabel("Inactive Sensors (Missing KeepAlive)")
        table_title.setFont(QFont("Segoe UI", 16))
        table_title.setStyleSheet("color: #1E293B; margin-bottom: 10px;")
        right_layout.addWidget(table_title)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Sensor Type", "Last Seen"])
        
        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)  # ID column
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Sensor Type
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Last Seen
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
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QTableWidget::item {
                padding: 10px;
            }
        """)
        right_layout.addWidget(self.table)
        lower_row.addWidget(right_frame, 2)

        main_layout.addLayout(lower_row)
        self.setStyleSheet("background-color: #F8FAFC;")
        self.setLayout(main_layout)

    # ============================================================
    # CREATE CARD
    # ============================================================
    def _create_status_card(self, title, value, color):
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border-radius: 16px;
                padding: 4px;
            }
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(6)

        # Colored circle at the top
        circle = QLabel()
        circle.setFixedSize(48, 48)
        circle.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 24px;
            }}
        """)
        layout.addWidget(circle, alignment=Qt.AlignmentFlag.AlignCenter)

        # Value
        val_label = QLabel(value)
        val_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        val_label.setStyleSheet("color: #1E293B;")
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(val_label)
        frame.value_label = val_label

        # Title
        name = QLabel(title)
        name.setFont(QFont("Segoe UI", 11))
        name.setStyleSheet("color: #64748B;")
        name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name.setWordWrap(True)
        layout.addWidget(name)
        
        return frame

    # ============================================================
    # 🔄 REFRESH DATA
    # ============================================================
    def refresh_data(self):
        try:
            print("\n[SensorsStatusSummary] ===== REFRESH DATA START =====")

            # === Load sensors ===
            res_sensors = self.api.http.get(f"{self.api.base}/api/tables/devices_sensor")
            sensors = res_sensors.json().get("rows", [])
            print(f"[SensorsStatusSummary] Loaded {len(sensors)} sensors")

            # === Load events incrementally ===
            if self._first_load:
                print("[SensorsStatusSummary] Initial load - fetching events...")
                # API limit is max 500 per request
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
                    self._last_event_id = max(self._last_event_id, max(e.get("id", 0) for e in new_events))
                    self._events_cache = self._events_cache[-5000:]
                else:
                    print("[SensorsStatusSummary] No new events")

            events = self._events_cache
            print(f"[SensorsStatusSummary] Total cached events: {len(events)}")

            # === Analyze ===
            latest_issues = self._get_latest_open_issues(events)
            
            # Categorize sensors by their LATEST issue type
            inactive = [e for e in latest_issues if e.get("issue_type") == "missing_keepalive"]
            outofrange = [e for e in latest_issues if e.get("issue_type") == "out_of_range"]
            corrupted = [e for e in latest_issues if e.get("issue_type") in ["corrupted", "stuck_sensor"]]

            print(f"[SensorsStatusSummary] Categorized by latest issue:")
            print(f"  - Inactive (missing_keepalive): {len(inactive)}")
            print(f"  - Out of range: {len(outofrange)}")
            print(f"  - Corrupted/Stuck: {len(corrupted)}")
            
            # Get unique sensor IDs with issues
            all_problematic_ids = {str(e.get("device_id")) for e in latest_issues if e.get("device_id")}
            print(f"  - Total unique sensors with issues: {len(all_problematic_ids)}")

            total = len(sensors)
            active = [s for s in sensors if str(s.get("id")) not in all_problematic_ids]
            health = int((len(active) / total * 100)) if total else 0
            
            print(f"[SensorsStatusSummary] Summary:")
            print(f"  - Total sensors: {total}")
            print(f"  - Active (no issues): {len(active)}")
            print(f"  - Health: {health}%")
            print(f"  - Verification: {len(active)} + {len(all_problematic_ids)} = {len(active) + len(all_problematic_ids)} (should equal {total})")

            # === Update UI ===
            self.active_card.value_label.setText(str(len(active)))
            self.inactive_card.value_label.setText(str(len(inactive)))
            self.outofrange_card.value_label.setText(str(len(outofrange)))
            self.corrupted_card.value_label.setText(str(len(corrupted)))

            self.health_ring.value = health
            self.health_ring.update()
            self.ring_bottom.setText(f"{len(active)} active sensors of {total}")

            # Update last refresh time
            now = datetime.now(timezone.utc)
            time_str = now.strftime("%H:%M:%S")
            self.status_badge.setText(f"Live • Updated at {time_str}")

            self._update_inactive_table(inactive, sensors)
            print("[SensorsStatusSummary] ===== REFRESH DATA END =====\n")

        except Exception as e:
            print(f"[SensorsStatusSummary] ❌ ERROR refreshing data: {e}")
            import traceback
            traceback.print_exc()

    # ============================================================
    # 🔍 GET LATEST OPEN ISSUES
    # ============================================================
    def _get_latest_open_issues(self, events):
        """
        Get the MOST RECENT open issue per sensor (only ONE issue per sensor).
        If a sensor has multiple open issues, only the latest (highest ID) is returned.
        """
        latest_per_sensor = {}
        
        for e in events:
            dev_id = e.get("device_id")
            if dev_id is None or e.get("end_ts") is not None:
                continue
            
            dev_id_str = str(dev_id)
            event_id = e.get("id", 0)
            
            # Keep only the event with the highest ID for each sensor
            if dev_id_str not in latest_per_sensor or event_id > latest_per_sensor[dev_id_str].get("id", 0):
                latest_per_sensor[dev_id_str] = e
        
        result = list(latest_per_sensor.values())
        print(f"[_get_latest_open_issues] Processed {len(events)} events")
        print(f"[_get_latest_open_issues] Found {len(result)} sensors with open issues (1 issue per sensor)")
        
        # Debug: show distribution
        if result:
            types_count = {}
            for issue in result:
                itype = issue.get("issue_type", "unknown")
                types_count[itype] = types_count.get(itype, 0) + 1
            print(f"[_get_latest_open_issues] Distribution: {types_count}")
        
        return result

    # ============================================================
    # 📋 UPDATE TABLE
    # ============================================================
    def _update_inactive_table(self, inactive_events, sensors):
        self.table.setRowCount(0)
        now = datetime.now(timezone.utc)
        sensor_map = {str(s.get("id")): s for s in sensors}

        # Sort by device_id
        sorted_events = sorted(inactive_events, key=lambda e: int(e.get("device_id", 0)))

        for ev in sorted_events:
            dev_id = str(ev.get("device_id"))
            sensor = sensor_map.get(dev_id)
            if not sensor:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            last_seen = sensor.get("last_seen")
            # Format to show only time (HH:MM:SS)
            try:
                dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                time_str = dt.strftime("%H:%M:%S")
            except Exception:
                time_str = "—"

            # ID column
            id_item = QTableWidgetItem(dev_id)
            self.table.setItem(row, 0, id_item)
            
            # Sensor Type
            self.table.setItem(row, 1, QTableWidgetItem(sensor.get("sensor_type", "Unknown")))
            
            # Last Seen - only time, highlighted
            last_seen_item = QTableWidgetItem(time_str)
            last_seen_item.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            last_seen_item.setForeground(QColor("#DC2626"))  # Red color for emphasis
            self.table.setItem(row, 2, last_seen_item)
