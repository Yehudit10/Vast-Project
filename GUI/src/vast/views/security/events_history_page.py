from PyQt6 import QtWidgets, QtGui, QtCore
import os, sys, vlc
from datetime import datetime


class EventsHistoryPage(QtWidgets.QWidget):
    """AgGuard Security Events History — visual-only severity bar with sorting and fixed filters (with debug prints)."""

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setContentsMargins(24, 24, 24, 24)

        print("[INIT] EventsHistoryPage initialized")

        # ───────────── GLOBAL STYLE ─────────────
        self.setStyleSheet("""
            QWidget {
                background-color: #f9fafb;
                font-family: 'Segoe UI', 'DejaVu Sans', Arial, sans-serif;
                color: #111827;
                font-size: 14px;
            }
            QHeaderView::section {
                background-color: #f3f4f6;
                color: #111827;
                font-weight: 600;
                border: none;
                padding: 8px;
                border-bottom: 1px solid #e5e7eb;
            }
            QTableWidget {
                gridline-color: #e5e7eb;
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 10px;
                selection-background-color: #bbf7d0;
                selection-color: #065f46;
                font-size: 13px;
            }
            QTableWidget::item { padding: 10px; }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #9ca3af;
                border-radius: 5px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #6b7280; }
            QComboBox, QDateEdit {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 13px;
                height: 32px;
                min-width: 120px;
                color: #111827;
            }
            QComboBox:hover, QDateEdit:hover {
                border-color: #9ca3af;
                background-color: #f9fafb;
            }
            QComboBox:focus, QDateEdit:focus {
                border: 1px solid #10b981;
                background-color: #ffffff;
            }
            QComboBox QAbstractItemView {
                border: none;
                background-color: #ffffff;
                padding: 6px 4px;
                outline: none;
                font-size: 14px;
                selection-background-color: #10b981;
                selection-color: white;
            }
            QPushButton {
                border: none;
                border-radius: 6px;
                font-weight: 500;
                padding: 6px 12px;
            }
            QPushButton#reload_btn {
                background-color: #10b981;
                color: white;
                font-weight: 600;
            }
            QPushButton#reload_btn:hover { background-color: #059669; }
            QPushButton#clear_btn {
                background-color: #f3f4f6;
                color: #374151;
                border: 1px solid #d1d5db;
            }
            QPushButton#clear_btn:hover { background-color: #e5e7eb; }
            QPushButton.view_btn {
                background-color: #10b981;
                color: white;
                padding: 6px 16px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton.view_btn:hover { background-color: #059669; }
        """)

        # ───────────── CONSTANTS ─────────────
        self.media_proxy_base = os.getenv("MEDIA_PROXY_BASE", "http://media-proxy:8080").rstrip("/")
        self.proxy_local_base = "http://127.0.0.1:19100"
        self.all_rows = []

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(18)

        # ───────────── HEADER ─────────────
        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("🧾 Security Events History")
        title.setStyleSheet("font-size:22px;font-weight:700;color:#0f172a;")
        header.addWidget(title)
        header.addStretch(1)

        reload_btn = QtWidgets.QPushButton("Reload")
        reload_btn.setObjectName("reload_btn")
        reload_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        reload_btn.clicked.connect(self.load_from_api)
        header.addWidget(reload_btn)
        main_layout.addLayout(header)

        # ───────────── TOOLBAR ─────────────
        toolbar = QtWidgets.QFrame()
        toolbar.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 14px;
                padding: 10px 14px;
            }
        """)
        tl = QtWidgets.QHBoxLayout(toolbar)
        tl.setContentsMargins(8, 6, 8, 6)
        tl.setSpacing(8)

        self.device_filter = QtWidgets.QComboBox()
        self.device_filter.addItem("All Devices")
        self.device_filter.currentIndexChanged.connect(self.apply_filters)

        self.anomaly_filter = QtWidgets.QComboBox()
        self.anomaly_filter.addItem("All Anomalies")
        self.anomaly_filter.currentIndexChanged.connect(self.apply_filters)

        self.severity_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.severity_slider.setRange(0, 6)
        self.severity_slider.setFixedWidth(110)
        self._update_slider_style(0)
        self.severity_slider.valueChanged.connect(self._update_slider_style)
        self.severity_slider.valueChanged.connect(self.apply_filters)

        self.from_date = QtWidgets.QDateEdit(QtCore.QDate.currentDate().addMonths(-1))
        self.from_date.setDisplayFormat("yyyy-MM-dd")
        self.from_date.setCalendarPopup(True)
        self.from_date.dateChanged.connect(self.apply_filters)

        self.to_date = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.to_date.setDisplayFormat("yyyy-MM-dd")
        self.to_date.setCalendarPopup(True)
        self.to_date.dateChanged.connect(self.apply_filters)

        self.sort_combo = QtWidgets.QComboBox()
        self.sort_combo.addItems([
            "No Sorting",
            "Severity (High → Low)",
            "Severity (Low → High)",
            "Start Time (Newest)",
            "Start Time (Oldest)",
            "End Time (Newest)",
            "End Time (Oldest)",
            "Anomaly (A → Z)",
            "Anomaly (Z → A)"
        ])
        self.sort_combo.currentIndexChanged.connect(self.apply_filters)

        clear_btn = QtWidgets.QPushButton("Clear")
        clear_btn.setObjectName("clear_btn")
        clear_btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        clear_btn.clicked.connect(self.clear_filters)

        for w in [
            self.device_filter, self.anomaly_filter,
            self.severity_slider, self.from_date, self.to_date,
            self.sort_combo
        ]:
            tl.addWidget(w)
        tl.addStretch(1)
        tl.addWidget(clear_btn)
        main_layout.addWidget(toolbar)

        # ───────────── TABLE ─────────────
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels([
            "ID", "Device", "Anomaly", "Start Time",
            "End Time", "Duration (s)", "Severity", "View"
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(48)
        main_layout.addWidget(self.table, 1)

        QtCore.QTimer.singleShot(300, self.load_from_api)

    # ───────────── SLIDER STYLE ─────────────
    def _update_slider_style(self, value):
        percent = value / 6 if value else 0
        self.severity_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 1px solid #d1d5db;
                height: 6px;
                border-radius: 3px;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #10b981,
                    stop:{percent} #10b981,
                    stop:{percent} white,
                    stop:1 white
                );
            }}
            QSlider::handle:horizontal {{
                width: 16px;
                height: 16px;
                background: #10b981;
                border-radius: 8px;
                margin: -5px 0;
                border: 1px solid #10b981;
            }}
        """)

    # ───────────── LOGIC ─────────────
    def _safe_int(self, val):
        try:
            return int(val)
        except Exception:
            return 0

    def _parse_time(self, t):
        try:
            if not t:
                return None
            dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None)
        except Exception:
            return None

    def _fmt_time(self, t):
        return t.replace("T", " ").split(".")[0] if t else "-"

    def load_from_api(self):
        print("[API] Fetching incidents from:", f"{self.api.base}/api/incidents")
        try:
            url = f"{self.api.base}/api/incidents"
            resp = self.api.http.get(url, timeout=8)
            resp.raise_for_status()
            self.all_rows = resp.json()
            print(f"[API] Loaded {len(self.all_rows)} incidents.")
        except Exception as e:
            print("[API][ERROR]", e)
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to fetch incidents:\n{e}")
            return
        self.populate_table(self.all_rows)
        self.populate_filters()

    def populate_filters(self):
        devices = sorted({it.get("device_id") or "-" for it in self.all_rows})
        anomalies = sorted({it.get("anomaly") or "-" for it in self.all_rows})
        print(f"[FILTERS] Available devices={devices}")
        print(f"[FILTERS] Available anomalies={anomalies}")

        # devices
        self.device_filter.blockSignals(True)
        self.device_filter.clear()
        self.device_filter.addItem("All Devices", None)
        for d in devices:
            self.device_filter.addItem(d, d)
        self.device_filter.blockSignals(False)

        # anomalies (friendly display)
        self.anomaly_filter.blockSignals(True)
        self.anomaly_filter.clear()
        self.anomaly_filter.addItem("All Anomalies", None)
        for a in anomalies:
            label = a.replace("_", " ").title() if a and a != "-" else a
            self.anomaly_filter.addItem(label, a)
        self.anomaly_filter.blockSignals(False)

        print("[FILTERS] Filters populated.")

    def apply_filters(self):
        if not self.all_rows:
            print("[FILTER] No rows loaded yet.")
            return

        device = self.device_filter.currentData()
        anomaly = self.anomaly_filter.currentData()
        min_sev = self._safe_int(self.severity_slider.value())
        from_dt = datetime.combine(self.from_date.date().toPyDate(), datetime.min.time())
        to_dt = datetime.combine(self.to_date.date().toPyDate(), datetime.max.time())

        print(f"\n[FILTER] Applying filters:")
        print(f"         device={device}, anomaly={anomaly}, min_sev={min_sev},")
        print(f"         from={from_dt}, to={to_dt}")
        print(f"         total rows={len(self.all_rows)}")

        filtered = []
        for idx, it in enumerate(self.all_rows):
            dev = it.get("device_id") or "-"
            anom = it.get("anomaly") or "-"
            sev = self._safe_int(it.get("severity"))
            started = self._parse_time(it.get("started_at"))

            include = True
            reasons = []

            # Device filter
            if device and dev != device:
                include = False
                reasons.append(f"device mismatch ({dev} ≠ {device})")

            # Anomaly filter
            if anomaly and anom != anomaly:
                include = False
                reasons.append(f"anomaly mismatch ({anom} ≠ {anomaly})")

            # Severity filter
            if sev < min_sev:
                include = False
                reasons.append(f"severity too low ({sev} < {min_sev})")

            # Date filter
            if started:
                if not (from_dt <= started <= to_dt):
                    include = False
                    reasons.append(f"date {started} out of range [{from_dt}, {to_dt}]")
            else:
                reasons.append("no start date parsed")

            if include:
                filtered.append(it)
            else:
                print(f"[FILTER][X] Row {idx} excluded — {', '.join(reasons)}")

        print(f"[FILTER] {len(filtered)} / {len(self.all_rows)} rows matched filters.\n")

        # Sorting
        i = self.sort_combo.currentIndex()
        keymap = {
            1: lambda x: self._safe_int(x.get("severity")),
            2: lambda x: self._safe_int(x.get("severity")),
            3: lambda x: self._parse_time(x.get("started_at")) or datetime.min,
            4: lambda x: self._parse_time(x.get("started_at")) or datetime.min,
            5: lambda x: self._parse_time(x.get("ended_at")) or datetime.min,
            6: lambda x: self._parse_time(x.get("ended_at")) or datetime.min,
            7: lambda x: (x.get("anomaly") or "").lower(),
            8: lambda x: (x.get("anomaly") or "").lower(),
        }

        if i in keymap:
            reverse = i in (1, 3, 5, 8)
            print(f"[SORT] Sorting index={i}, reverse={reverse}")
            filtered.sort(key=keymap[i], reverse=reverse)
        else:
            print("[SORT] No sorting applied.")

        self.populate_table(filtered)


    def clear_filters(self):
        print("[FILTER] Clearing filters to defaults.")
        self.device_filter.setCurrentIndex(0)
        self.anomaly_filter.setCurrentIndex(0)
        self.sort_combo.setCurrentIndex(0)
        self.severity_slider.setValue(0)
        self.from_date.setDate(QtCore.QDate.currentDate().addMonths(-1))
        self.to_date.setDate(QtCore.QDate.currentDate())
        self.apply_filters()

    def _severity_color(self, sev: int) -> str:
        """Return green intensity from white (low) to dark green (high)."""
        sev = max(1, min(sev, 9))
        # interpolate white (#ffffff) → dark green (#059669)
        def lerp_color(c1, c2, t):
            c1, c2 = [int(c1[i:i+2], 16) for i in (1, 3, 5)], [int(c2[i:i+2], 16) for i in (1, 3, 5)]
            mix = [round(c1[j] + (c2[j]-c1[j])*t) for j in range(3)]
            return f"#{mix[0]:02x}{mix[1]:02x}{mix[2]:02x}"
        return lerp_color("#ffffff", "#059669", sev / 9)

    def _severity_label(self, sev: int) -> str:
        if sev <= 3:
            return f"Low ({sev})"
        elif sev <= 6:
            return f"Medium ({sev})"
        else:
            return f"Critical ({sev})"





    def populate_table(self, rows):
        print(f"[TABLE] Populating table with {len(rows)} rows.")
        self.table.setRowCount(len(rows))

        for r, it in enumerate(rows):
            sid = (str(it.get("incident_id") or "")[:8] + "...") if it.get("incident_id") else "-"
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(sid))
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(it.get("device_id") or "-"))
            anomaly_label = (it.get("anomaly") or "-").replace("_", " ").title()
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(anomaly_label))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(self._fmt_time(it.get("started_at"))))
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(self._fmt_time(it.get("ended_at"))))
            self.table.setItem(r, 5, QtWidgets.QTableWidgetItem(str(it.get("duration_sec") or 0)))

           # ────── SEVERITY BAR (layout-based, reliable) ──────
            sev = self._safe_int(it.get("severity"))
            sev = max(1, min(sev, 9))
            fill = sev / 9.0

            if sev <= 3:
                label_text = "Low"
                color = "#a7f3d0"
            elif sev <= 6:
                label_text = "Medium"
                color = "#34d399"
            else:
                label_text = "High"
                color = "#059669"

            # Background container (taller bar)
            container = QtWidgets.QFrame()
            container.setFixedHeight(22)  # taller
            container.setStyleSheet("""
                QFrame {
                    background: #e5e7eb;
                    border: 1px solid #d1d5db;
                    border-radius: 10px;
                }
            """)

            # Grid layout (bar + label overlay)
            layout = QtWidgets.QGridLayout(container)
            layout.setContentsMargins(1, 1, 1, 1)
            layout.setSpacing(0)

            # Fill bar (shorter horizontal width, rounded edges)
            fill_bar = QtWidgets.QFrame(container)
            fill_bar.setStyleSheet(f"background-color: {color}; border-radius: 9px;")

            # Compute proportional pixel width (shorter bar)
            container_width = 90
            fill_bar.setFixedWidth(int(container_width * fill))

            layout.addWidget(fill_bar, 0, 0)
            layout.setColumnStretch(0, 0)
            layout.setColumnStretch(1, 1)

            # Centered transparent label overlay
            label = QtWidgets.QLabel(label_text, container)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-weight:600; color:#064e3b; background:transparent; font-size:13px;")
            layout.addWidget(label, 0, 0, 1, 2)

            # Wrap container for centering in cell
            wrapper = QtWidgets.QWidget()
            outer = QtWidgets.QHBoxLayout(wrapper)
            outer.setContentsMargins(4, 0, 4, 0)
            outer.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(container)
            self.table.setCellWidget(r, 6, wrapper)




            # ────── CENTERED VIEW BUTTON ──────
            btn = QtWidgets.QPushButton("View")
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(26)
            btn.setFixedWidth(65)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #10b981;
                    color: white;
                    border-radius: 6px;
                    font-size: 12px;
                    font-weight: 600;
                    padding: 3px 6px;
                }
                QPushButton:hover {
                    background-color: #059669;
                }
            """)
            btn.clicked.connect(lambda _, info=it: self._open_video_player(info))

            btn_container = QtWidgets.QWidget()
            btn_layout = QtWidgets.QHBoxLayout(btn_container)
            btn_layout.setContentsMargins(0, 0, 0, 0)
            btn_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            btn_layout.addWidget(btn)
            self.table.setCellWidget(r, 7, btn_container)

        print("[TABLE] Done populating table.")






    def _open_video_player(self, info):
        print(f"[VIDEO] Opening video player for incident={info.get('incident_id')} device={info.get('device_id')}")
        cam, iid = info.get("device_id") or "unknown", info.get("incident_id") or "0"
        url = f"{self.media_proxy_base}/vod/{cam}/{iid}/final.mp4"
        final_url = f"{self.proxy_local_base}/vod?u={url}"
        self._show_vlc_popup(final_url)

    def _show_vlc_popup(self, url):
        print(f"[VIDEO] Playing URL: {url}")
        popup = QtWidgets.QDialog(self)
        popup.setWindowTitle("Incident Video Playback")
        popup.setMinimumSize(640, 400)
        vbox = QtWidgets.QVBoxLayout(popup)
        player = QtWidgets.QFrame()
        player.setStyleSheet("background:black;border-radius:8px;")
        vbox.addWidget(player, 1)
        inst = vlc.Instance(["--quiet", "--no-video-title-show"])
        mp = inst.media_player_new()
        mp.set_media(inst.media_new(url))
        popup.show()
        if sys.platform.startswith("win"):
            mp.set_hwnd(int(player.winId()))
        else:
            mp.set_xwindow(int(player.winId()))
        mp.play()
        print("[VIDEO] Playback started.")
