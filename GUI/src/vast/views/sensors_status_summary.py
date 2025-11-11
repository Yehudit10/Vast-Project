from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QPushButton
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from datetime import datetime, timedelta


class SensorsStatusSummary(QWidget):
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        
        # Cache for performance optimization
        self._last_sensors_fetch = None
        self._sensors_cache = []
        self._last_events_check = None
        self._events_cache = []
        self._last_event_id = 0  # Track last processed event ID
        
        # Cache duration (5 minutes for sensors, 1 minute for events)
        self._sensors_cache_duration = timedelta(minutes=5)
        self._events_cache_duration = timedelta(minutes=1)
        
        self._build_ui()
        self.load_data()
        
        # Auto-refresh timer for events only (every 30 seconds)
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_events_only)
        self._refresh_timer.start(30000)  # 30 seconds

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(30, 30, 30, 30)
        main_layout.setSpacing(25)

        # -------- MODERN HEADER --------
        header_layout = QVBoxLayout()
        
        title = QLabel("🌾 Sensors Status Dashboard")
        title.setStyleSheet("""
            QLabel {
                font-family: 'Segoe UI', 'Roboto', 'Inter', sans-serif;
                font-size: 32px; 
                font-weight: 800;
                color: #1a1a1a;
                margin-bottom: 8px;
                letter-spacing: -0.5px;
            }
        """)
        
        subtitle = QLabel("Real-time monitoring of agricultural sensors")
        subtitle.setStyleSheet("""
            QLabel {
                font-family: 'Segoe UI', 'Roboto', 'Inter', sans-serif;
                font-size: 16px;
                font-weight: 400;
                color: #6B7280;
                margin-bottom: 15px;
            }
        """)
        
        header_layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignLeft)
        header_layout.addWidget(subtitle, alignment=Qt.AlignmentFlag.AlignLeft)
        main_layout.addLayout(header_layout)

        # -------- MODERN STATUS CARDS --------
        cards_row = QHBoxLayout()
        cards_row.setSpacing(20)
        self.active_card = self._create_status_card("Active Sensors", "●", "#10B981", "#F0FDF4")
        self.inactive_card = self._create_status_card("Inactive Sensors", "●", "#EF4444", "#FEF2F2")
        cards_row.addWidget(self.active_card)
        cards_row.addWidget(self.inactive_card)
        main_layout.addLayout(cards_row)

        # -------- MODERN TABLE --------
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Sensor Type", "Plant", "Plant ID", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background-color: #ffffff;
                alternate-background-color: #F9FAFB;
                font-family: 'Segoe UI', 'Roboto', 'Inter', sans-serif;
                font-size: 14px;
                border: 2px solid #E5E7EB;
                border-radius: 12px;
                gridline-color: #F3F4F6;
                selection-background-color: #EEF2FF;
            }
            QHeaderView::section {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #F8FAFC, stop: 1 #F1F5F9);
                font-family: 'Segoe UI', 'Roboto', 'Inter', sans-serif;
                font-weight: 700;
                font-size: 15px;
                color: #1F2937;
                border: none;
                border-bottom: 2px solid #E5E7EB;
                padding: 12px 8px;
                text-align: left;
            }
            QTableWidget::item {
                padding: 12px 8px;
                border-bottom: 1px solid #F3F4F6;
            }
            QTableWidget::item:selected {
                background-color: #EEF2FF;
                color: #1E40AF;
            }
            QTableWidget::item:hover {
                background-color: #F8FAFC;
            }
        """)
        main_layout.addWidget(self.table)

        # -------- MODERN REFRESH BUTTON --------
        button_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("↻ Refresh Data")
        refresh_btn.setFixedWidth(150)
        refresh_btn.setFixedHeight(45)
        refresh_btn.clicked.connect(self.refresh_all)
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #3B82F6, stop: 1 #1D4ED8);
                color: white;
                border-radius: 12px;
                font-family: 'Segoe UI', 'Roboto', 'Inter', sans-serif;
                font-size: 15px;
                font-weight: 600;
                padding: 0px 16px;
                border: none;
                letter-spacing: 0.3px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2563EB, stop: 1 #1E40AF);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1D4ED8, stop: 1 #1E3A8A);
            }
        """)
        
        button_layout.addStretch()
        button_layout.addWidget(refresh_btn)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #F8FAFC, stop: 1 #F1F5F9);
                font-family: 'Segoe UI', 'Roboto', 'Inter', sans-serif;
            }
        """)

    # -------- MODERN CARD CREATOR --------
    def _create_status_card(self, title_text, icon, accent_color, bg_color):
        frame = QFrame()
        frame.setFixedHeight(120)
        frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 {bg_color}, stop: 1 #ffffff);
                border-radius: 16px;
                border: none;
                padding: 0px;
            }}
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(18)

        # Icon section
        icon_label = QLabel(icon)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setFixedSize(50, 50)
        icon_label.setStyleSheet(f"""
            QLabel {{
                color: {accent_color};
                font-size: 36px;
                font-weight: 900;
                background: transparent;
                border-radius: 25px;
                font-family: 'Segoe UI Symbol', 'Arial';
            }}
        """)
        layout.addWidget(icon_label)

        # Text section
        text_layout = QVBoxLayout()
        text_layout.setSpacing(5)
        
        title = QLabel(title_text)
        title.setStyleSheet(f"""
            QLabel {{
                font-family: 'Segoe UI', 'Roboto', 'Inter', sans-serif;
                font-size: 16px; 
                font-weight: 600; 
                color: #374151;
                letter-spacing: 0.2px;
            }}
        """)
        
        count = QLabel("0")
        count.setObjectName(title_text.lower().replace(" ", "_"))
        count.setStyleSheet(f"""
            QLabel {{
                font-family: 'Segoe UI', 'Roboto', 'Inter', sans-serif;
                font-size: 32px; 
                font-weight: 800; 
                color: {accent_color};
                letter-spacing: -1px;
            }}
        """)
        
        text_layout.addWidget(title)
        text_layout.addWidget(count)
        layout.addLayout(text_layout)

        return frame

    # -------- LOAD DATA (OPTIMIZED) --------
    def load_data(self, force_sensors_refresh=False):
        """Load sensors and events data with caching optimization."""
        try:
            # Load sensors (with caching)
            sensors = self._get_sensors_cached(force_sensors_refresh)
            
            # Load recent keepalive events only (last 2 hours for performance)
            events = self._get_recent_keepalive_events()
            
        except Exception as e:
            print("[SensorsStatusSummary] Error loading data:", e)
            return

        # identify inactive sensors by looking at the LATEST record for each device
        inactive_ids = set()
        
        # Group events by device_id and issue_type
        device_latest = {}
        
        for e in events:
            if (e.get("issue_type") in ["missing_keepalive", "prolonged_silence"] 
                and str(e.get("device_id", "")).isdigit()):
                device_id = str(e["device_id"])
                issue_type = e.get("issue_type")
                key = f"{device_id}_{issue_type}"
                
                # Keep only the latest record for each device+issue_type combination
                if key not in device_latest:
                    device_latest[key] = e
                else:
                    # Compare by ID (higher ID = more recent) since start_ts can be identical
                    current_id = device_latest[key].get("id", 0)
                    new_id = e.get("id", 0)
                    if new_id > current_id:
                        device_latest[key] = e
        
        # Now check which devices have open issues based on latest records
        for key, latest_event in device_latest.items():
            if latest_event.get("end_ts") is None:  # Latest record is still open
                device_id = str(latest_event["device_id"])
                inactive_ids.add(device_id)
        
        print(f"[SensorsStatusSummary] Found {len(inactive_ids)} sensors with active keepalive issues (based on latest records)")

        active = [s for s in sensors if s["id"] not in inactive_ids]
        inactive = [s for s in sensors if s["id"] in inactive_ids]

        print(f"[SensorsStatusSummary] Status: {len(active)} active, {len(inactive)} inactive sensors")
        print(f"[SensorsStatusSummary] DEBUG: inactive_ids = {sorted(inactive_ids)}")
        print(f"[SensorsStatusSummary] DEBUG: sensor IDs = {[s['id'] for s in sensors]}")
        print(f"[SensorsStatusSummary] DEBUG: active sensor IDs = {[s['id'] for s in active]}")
        print(f"[SensorsStatusSummary] DEBUG: inactive sensor IDs = {[s['id'] for s in inactive]}")
        
        # Debug: show which sensors are inactive
        if inactive_ids:
            print(f"[SensorsStatusSummary] Inactive sensor IDs: {sorted(inactive_ids)}")

        self._update_cards(active, inactive)
        self._update_table(active, inactive)

    def _get_sensors_cached(self, force_refresh=False):
        """Get sensors list with caching (sensors don't change often)."""
        now = datetime.now()
        
        if (not force_refresh and 
            self._last_sensors_fetch and 
            self._sensors_cache and
            (now - self._last_sensors_fetch) < self._sensors_cache_duration):
            return self._sensors_cache
            
        # Fetch fresh sensors data
        res_sensors = self.api.http.get(f"{self.api.base}/api/tables/devices_sensor")
        self._sensors_cache = res_sensors.json().get("rows", [])
        self._last_sensors_fetch = now
        print(f"[SensorsStatusSummary] Refreshed sensors cache: {len(self._sensors_cache)} sensors")
        return self._sensors_cache

    def _get_recent_keepalive_events(self):
        """Get events with smart caching - only fetch new events since last check."""
        now = datetime.now()
        
        # Check if cache is still valid
        if (self._last_events_check and 
            self._events_cache and
            (now - self._last_events_check) < self._events_cache_duration):
            return self._events_cache
        
        try:
            # Strategy: Get only NEW events since last check (incremental loading)
            if self._last_event_id > 0:
                # Get only events with ID > last processed ID
                url = f"{self.api.base}/api/tables/event_logs_sensors?limit=200&order_by=id&order_dir=desc"
                res_events = self.api.http.get(url)
                new_events = res_events.json().get("rows", [])
                
                # Filter only truly new events
                really_new = [e for e in new_events if e.get("id", 0) > self._last_event_id]
                
                if really_new:
                    print(f"[SensorsStatusSummary] Found {len(really_new)} new events")
                    # Update cache with new events
                    self._update_events_cache(really_new)
                else:
                    print("[SensorsStatusSummary] No new events since last check")
            else:
                # First load - get recent events
                print("[SensorsStatusSummary] First load - fetching initial events")
                url = f"{self.api.base}/api/tables/event_logs_sensors?limit=500&order_by=id&order_dir=desc"
                res_events = self.api.http.get(url)
                all_events = res_events.json().get("rows", [])
                self._initialize_events_cache(all_events)
            
            self._last_events_check = now
            return self._events_cache
            
        except Exception as e:
            print(f"[SensorsStatusSummary] Error loading events: {e}")
            return self._events_cache or []

    def _initialize_events_cache(self, all_events):
        """Initialize cache on first load."""
        # Filter relevant events and store in cache
        two_hours_ago = datetime.now() - timedelta(hours=2)
        
        filtered_events = []
        max_id = 0
        
        for event in all_events:
            event_id = event.get("id", 0)
            if event_id > max_id:
                max_id = event_id
            
            # Check issue type
            if event.get("issue_type") not in ["missing_keepalive", "prolonged_silence"]:
                continue
            
            # Keep both open events AND recently closed events (for cache invalidation)
            is_open = event.get("end_ts") is None
            is_recently_closed = False
            
            if not is_open:
                # Check if closed recently (last 5 minutes)
                end_ts_str = event.get("end_ts")
                if end_ts_str:
                    try:
                        end_ts = datetime.fromisoformat(end_ts_str.replace('Z', '+00:00'))
                        five_min_ago = datetime.now() - timedelta(minutes=5)
                        is_recently_closed = end_ts.replace(tzinfo=None) >= five_min_ago
                    except (ValueError, AttributeError):
                        pass
            
            # Keep only open events or recently closed ones
            if not (is_open or is_recently_closed):
                continue
            
            # Check if recent (within last 2 hours)
            start_ts_str = event.get("start_ts")
            if start_ts_str:
                try:
                    start_ts = datetime.fromisoformat(start_ts_str.replace('Z', '+00:00'))
                    if start_ts.replace(tzinfo=None) < two_hours_ago:
                        continue  # Too old
                except (ValueError, AttributeError):
                    continue  # Invalid timestamp
            
            filtered_events.append(event)
        
        self._events_cache = filtered_events
        self._last_event_id = max_id
        print(f"[SensorsStatusSummary] Initialized cache with {len(filtered_events)} relevant events")

    def _update_events_cache(self, new_events):
        """Update cache with new events (incremental)."""
        two_hours_ago = datetime.now() - timedelta(hours=2)
        
        # Process new events
        new_relevant = []
        max_id = self._last_event_id
        
        for event in new_events:
            event_id = event.get("id", 0)
            if event_id > max_id:
                max_id = event_id
            
            # Apply same filtering (include recent closures)
            if event.get("issue_type") in ["missing_keepalive", "prolonged_silence"]:
                is_open = event.get("end_ts") is None
                is_recently_closed = False
                
                if not is_open:
                    end_ts_str = event.get("end_ts")
                    if end_ts_str:
                        try:
                            end_ts = datetime.fromisoformat(end_ts_str.replace('Z', '+00:00'))
                            five_min_ago = datetime.now() - timedelta(minutes=5)
                            is_recently_closed = end_ts.replace(tzinfo=None) >= five_min_ago
                        except (ValueError, AttributeError):
                            pass
                
                if is_open or is_recently_closed:
                    # Check if recent
                    start_ts_str = event.get("start_ts")
                    if start_ts_str:
                        try:
                            start_ts = datetime.fromisoformat(start_ts_str.replace('Z', '+00:00'))
                            if start_ts.replace(tzinfo=None) >= two_hours_ago:
                                new_relevant.append(event)
                        except (ValueError, AttributeError):
                            pass
        
        # Update cache: add new events and remove old ones
        self._events_cache.extend(new_relevant)
        
        # Clean old events from cache (older than 2 hours)
        self._events_cache = [
            e for e in self._events_cache
            if self._is_event_recent(e, two_hours_ago)
        ]
        
        self._last_event_id = max_id
        print(f"[SensorsStatusSummary] Added {len(new_relevant)} new events, cache now has {len(self._events_cache)} events")

    def _is_event_recent(self, event, threshold):
        """Check if event is recent enough to keep in cache."""
        start_ts_str = event.get("start_ts")
        if not start_ts_str:
            return True  # Keep if no timestamp
        
        try:
            start_ts = datetime.fromisoformat(start_ts_str.replace('Z', '+00:00'))
            return start_ts.replace(tzinfo=None) >= threshold
        except (ValueError, AttributeError):
            return True  # Keep if invalid timestamp

    def _refresh_events_only(self):
        """Auto-refresh only events data (called by timer)."""
        try:
            self.load_data(force_sensors_refresh=False)
        except Exception as e:
            print(f"[SensorsStatusSummary] Auto-refresh error: {e}")

    def refresh_all(self):
        """Force refresh all data (sensors + events) - clear all caches."""
        # Clear all caches
        self._events_cache = []
        self._last_event_id = 0
        self._last_events_check = None
        self._sensors_cache = []
        self._last_sensors_fetch = None
        
        print("[SensorsStatusSummary] Cleared all caches - doing full refresh")
        self.load_data(force_sensors_refresh=True)

    def _update_cards(self, active, inactive):
        self.active_card.findChild(QLabel, "active_sensors").setText(str(len(active)))
        self.inactive_card.findChild(QLabel, "inactive_sensors").setText(str(len(inactive)))

    def _update_table(self, active, inactive):
        all_data = [(s, "Active") for s in active] + [(s, "Inactive") for s in inactive]
        self.table.setRowCount(len(all_data))

        for r, (sensor, status) in enumerate(all_data):
            sid = QTableWidgetItem(str(sensor.get("id", "")))
            typ = QTableWidgetItem(sensor.get("sensor_type", ""))
            # devices_sensor table doesn't have owner_name, use plant_id instead
            plant_id = QTableWidgetItem(f"Plant {sensor.get('plant_id', '—')}")
            # devices_sensor table doesn't have location, show plant_id info instead
            location = QTableWidgetItem(f"Plant ID: {sensor.get('plant_id', 'N/A')}")
            # Modern status with colored badges
            if status == "Active":
                stat = QTableWidgetItem("● ONLINE")
                stat.setForeground(Qt.GlobalColor.darkGreen)
            else:
                stat = QTableWidgetItem("● OFFLINE")
                stat.setForeground(Qt.GlobalColor.darkRed)

            # Style inactive rows with subtle background
            if status == "Inactive":
                gray_bg = QColor(248, 250, 252)
                gray_text = QColor(107, 114, 128)
                
                for item in (sid, typ, plant_id, location):
                    item.setBackground(gray_bg)
                    item.setForeground(gray_text)

            self.table.setItem(r, 0, sid)
            self.table.setItem(r, 1, typ)
            self.table.setItem(r, 2, plant_id)
            self.table.setItem(r, 3, location)
            self.table.setItem(r, 4, stat)
