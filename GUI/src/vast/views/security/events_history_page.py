from PyQt6 import QtWidgets, QtGui, QtCore
import os, sys, vlc
from datetime import datetime
from PyQt6 import sip


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
                font-size: 16px;
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
                font-size: 15px;
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
                font-size: 14px;
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
                font-size: 16px;
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
                font-size: 15px;
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
            "Device", "Anomaly", "Start Time", "End Time",
            "Duration (m)", "Severity", "View", "Feedback"
        ])

        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(56)
        main_layout.addWidget(self.table, 1)
        # QtCore.QTimer.singleShot(300, self.load_from_api)
        self._load_timer = QtCore.QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(self._safe_load)
        self._load_timer.start(300)
    def _safe_load(self):
        if not self.isVisible() or sip.isdeleted(self.table):
            print("[SAFE_LOAD] Skipping load: widget closed or deleted.")
            return
        self.load_from_api()
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_loaded_once", False):
            self._loaded_once = True
            self.load_from_api()

    
    def closeEvent(self, event):
        print("[CLOSE] EventsHistoryPage closing — stopping load timer.")
        if hasattr(self, "_load_timer") and self._load_timer.isActive():
            self._load_timer.stop()
        return super().closeEvent(event)






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

    from datetime import datetime

    def _parse_time(self, t):
        if not t:
            return None

        try:
            # Normalize variants:
            # "2025-11-14 07:25:04+02:00"
            # "2025-11-14T07:25:04+02:00"
            # "2025-11-14 07:25:04Z"
            nt = t.replace(" ", "T").replace("Z", "+00:00")
            dt = datetime.fromisoformat(nt)

            # Convert to naive local time for table filtering
            return dt.astimezone().replace(tzinfo=None)

        except Exception:
            return None


    def _fmt_time(self, t):
        dt = self._parse_time(t)
        if not dt:
            return "-"
        return dt.strftime("%Y-%m-%d %H:%M:%S")


    def load_from_api(self):
        print("[API] Fetching alerts from:", f"{self.api.base}/api/tables/alerts")
        try:
            url = f"{self.api.base}/api/tables/alerts?limit=500"
            resp = self.api.http.get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()

            # Expect structure: {"rows": [...], "count": N}
            if isinstance(data, dict) and "rows" in data:
                rows = data["rows"]
                count = data.get("count", len(rows))
                print(f"[API] Loaded {count} total alerts.")
            else:
                rows = data if isinstance(data, list) else []
                print(f"[API][WARN] Unexpected format, using raw list of {len(rows)} items.")

            # ───── Filter only relevant alert types ─────
            allowed_types = {"climbing_fence", "masked_person", "intruding animal","fence_hole"}
            filtered = [r for r in rows if (r.get("alert_type") or "").strip() in allowed_types]

            print(f"[API] Filtered {len(filtered)} / {len(rows)} alerts matching allowed types {allowed_types}.")

            self.all_rows = filtered

        except Exception as e:
            print("[API][ERROR]", e)
            QtWidgets.QMessageBox.warning(self, "Error", f"Failed to fetch alerts:\n{e}")
            return

        # Update the table and filters
        self.populate_table(self.all_rows)
        self.populate_filters()



    def populate_filters(self):
        devices = sorted({it.get("device_id") or "-" for it in self.all_rows})
        anomalies = sorted({it.get("alert_type") or "-" for it in self.all_rows})

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
            anom = it.get("alert_type") or "-"
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
            7: lambda x: (x.get("alert_type") or "").lower(),
            8: lambda x: (x.get("alert_type") or "").lower(),
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
        if not hasattr(self, "table") or self.table is None:
            print("[TABLE][WARN] Table not available — widget probably closed.")
            return
        if sip.isdeleted(self.table):
            print("[TABLE][WARN] Table was deleted, aborting populate.")
            return
        print(f"[TABLE] Populating table with {len(rows)} alerts.")
        self.table.setRowCount(len(rows))

        for r, it in enumerate(rows):
            # Device
            self.table.setItem(r, 0, QtWidgets.QTableWidgetItem(it.get("device_id") or "-"))

            # Anomaly
            # Anomaly
            alert_type = it.get("alert_type") or "-"
            raw_meta = it.get("meta") or {}
            meta = {}

            if isinstance(raw_meta, dict):
                meta = raw_meta
            elif isinstance(raw_meta, str):
                try:
                    meta = json.loads(raw_meta)
                except Exception:
                    try:
                        import ast
                        meta = ast.literal_eval(raw_meta)
                    except Exception:
                        meta = {}

            subject = meta.get("subject")


            label = alert_type.replace("_", " ").title()
            if alert_type in ("intruding_animal","intruding animal", "climbing_fence") and subject:
                label = f"{label} ({subject.title()})"
            self.table.setItem(r, 1, QtWidgets.QTableWidgetItem(label))


            # Start / End time
            self.table.setItem(r, 2, QtWidgets.QTableWidgetItem(self._fmt_time(it.get("started_at"))))
            self.table.setItem(r, 3, QtWidgets.QTableWidgetItem(self._fmt_time(it.get("ended_at"))))

            # Duration (minutes)
            started = self._parse_time(it.get("started_at"))
            ended = self._parse_time(it.get("ended_at"))
            duration_m = "-"
            if started and ended:
                duration_m = f"{(ended - started).total_seconds() / 60:.1f}"
            self.table.setItem(r, 4, QtWidgets.QTableWidgetItem(duration_m))



          ## ────── SEVERITY BAR ──────
            sev = self._safe_int(it.get("severity"))
            sev = max(0, min(sev, 9))   # allow 0–9
            fill = sev / 9.0             # proportional fill

            if sev == 0:
                label_text = "None"
                color = "#f3f4f6"
            elif sev <= 3:
                label_text = "Low"
                color = "#a7f3d0"
            elif sev <= 6:
                label_text = "Medium"
                color = "#34d399"
            else:
                label_text = "High"
                color = "#059669"

            # Background container
            container = QtWidgets.QFrame()
            container.setFixedHeight(20)
            container.setStyleSheet("""
                QFrame {
                    background: #e5e7eb;
                    border: 1px solid #d1d5db;
                    border-radius: 8px;
                }
            """)

            layout = QtWidgets.QGridLayout(container)
            layout.setContentsMargins(1, 1, 1, 1)
            layout.setSpacing(0)

            fill_bar = QtWidgets.QFrame(container)
            fill_bar.setStyleSheet(f"background-color: {color}; border-radius: 7px;")

            # ↓ reduce bar width from 90 → 70 for better balance
            container_width = 150
            fill_bar.setFixedWidth(int(container_width * fill))

            layout.addWidget(fill_bar, 0, 0)
            layout.setColumnStretch(0, 0)
            layout.setColumnStretch(1, 1)

            label = QtWidgets.QLabel(label_text, container)
            label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("font-weight:600; color:#064e3b; background:transparent; font-size:12px;")
            layout.addWidget(label, 0, 0, 1, 2)

            wrapper = QtWidgets.QWidget()
            outer = QtWidgets.QHBoxLayout(wrapper)
            outer.setContentsMargins(2, 0, 2, 0)
            outer.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(container)
            self.table.setCellWidget(r, 5, wrapper)



            # Centered “View” button for vod
            btn = QtWidgets.QPushButton("View")
            btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(26)
            btn.setFixedWidth(65)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #10b981;
                    color: white;
                    border-radius: 6px;
                    font-size: 13px;
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
            self.table.setCellWidget(r, 6, btn_container)


            # ────── FEEDBACK (visible circular emoji buttons — no custom class) ──────
            feedback_widget = QtWidgets.QWidget(self.table)
            layout = QtWidgets.QHBoxLayout(feedback_widget)
            layout.setContentsMargins(0, 6, 0, 6)
            layout.setSpacing(12)
            layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

            thumb_up = QtWidgets.QPushButton("👍")
            thumb_down = QtWidgets.QPushButton("👎")

            for btn in (thumb_up, thumb_down):
                btn.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
                btn.setCheckable(True)
                btn.setFixedSize(48, 48)
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: white;
                        border-radius: 24px;
                        border: 2px solid #d1d5db;
                        font-size: 20px;
                    }
                    QPushButton:hover {
                        background-color: #f3f4f6;
                        border-color: #9ca3af;
                    }
                    QPushButton:checked {
                        background-color: #e5e7eb;
                        border-color: #4b5563;
                    }
                """)

            feedback_widget.thumb_up = thumb_up
            feedback_widget.thumb_down = thumb_down

            # Restore state
            meta = it.get("meta") or {}
            if isinstance(meta, str):
                import json
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            is_real = meta.get("is_real")
            if is_real is True:
                thumb_up.setChecked(True)
            elif is_real is False:
                thumb_down.setChecked(True)

            def handle_feedback_change(checked, alert=it, up_btn=thumb_up, down_btn=thumb_down):
                if not checked:
                    return
                is_real_value = up_btn.isChecked()
                down_btn.blockSignals(True)
                down_btn.setChecked(not is_real_value)
                down_btn.blockSignals(False)
                self._send_feedback(alert, is_real_value)

            thumb_up.toggled.connect(handle_feedback_change)
            thumb_down.toggled.connect(handle_feedback_change)

            layout.addWidget(thumb_up)
            layout.addWidget(thumb_down)
            feedback_widget.setLayout(layout)

            self.table.setRowHeight(r, 68)
            # Wrap feedback inside a centering wrapper
            cell_wrapper = QtWidgets.QWidget()
            cell_layout = QtWidgets.QHBoxLayout(cell_wrapper)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(feedback_widget)

            self.table.setCellWidget(r, 7, cell_wrapper)

            # self.table.setCellWidget(r, 7, feedback_widget)













        print("[TABLE] Done populating alerts table.")





           
    



    # def _open_video_player(self, info):
    #     print(f"[VIDEO] Opening video player for alert={info.get('alert_id')}")
    #     url = info.get("vod")
    #     if not url:
    #         QtWidgets.QMessageBox.warning(self, "No Video", "This alert has no VOD URL.")
    #         return
        

    def _open_video_player(self, info):
        print(f"[VIEW] Opening media for alert={info.get('alert_id')}")

        vod_url = info.get("vod")
        image_url = info.get("image_url")

        if vod_url:
            print("[VIEW] Found VOD — playing video.")
            proxy_url = f"http://127.0.0.1:19100/vod?u={self.media_proxy_base}/vod/{vod_url}"
            self._show_vlc_popup(proxy_url)
            return

        if image_url:
            print("[VIEW] No VOD, found image — showing image popup.")
            image_url = f"http://127.0.0.1:19100/vod?u={self.media_proxy_base}/img/{image_url}"
            self._show_image_popup(image_url)
            return

        QtWidgets.QMessageBox.warning(self, "No Media", "This alert has neither video nor image available.")
    
    def _show_image_popup(self, url: str):
        print(f"[IMAGE] Displaying still image from {url}")
        popup = QtWidgets.QDialog(self)
        popup.setWindowTitle("Incident Image")
        popup.setMinimumSize(640, 480)
        layout = QtWidgets.QVBoxLayout(popup)

        label = QtWidgets.QLabel()
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label, 1)

        # Fetch image via Qt network
        from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
        self._manager = QNetworkAccessManager()

        def handle_reply(reply):
            data = reply.readAll()
            pixmap = QtGui.QPixmap()
            if pixmap.loadFromData(data):
                label.setPixmap(pixmap.scaled(label.size(), QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation))
            else:
                label.setText("❌ Failed to load image.")
        self._manager.finished.connect(handle_reply)

        req = QNetworkRequest(QtCore.QUrl(url))
        self._manager.get(req)
        popup.exec()

    def _show_vlc_popup(self, url):
        print(f"[VIDEO] Playing URL: {url}")
        popup = QtWidgets.QDialog(self)
        popup.setWindowTitle("Incident Video Playback")
        popup.setMinimumSize(1280, 720)
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
    # def _show_vlc_popup(self, url):
    #     print(f"[VIDEO] Playing URL: {url}")

    #     popup = QtWidgets.QDialog(self)
    #     popup.setWindowTitle("Incident Video Playback")
    #     popup.setMinimumSize(1280, 720)
    #     vbox = QtWidgets.QVBoxLayout(popup)

    #     player = QtWidgets.QFrame()
    #     player.setStyleSheet("background:black;border-radius:8px;")
    #     vbox.addWidget(player, 1)

    #     # --- VLC instance with MP4-friendly options ---
    #     inst = vlc.Instance([
    #         "--quiet",
    #         "--no-video-title-show",
    #         "--demux=avformat",         # important for MP4
    #         "--network-caching=800",
    #         "--file-caching=800",
    #         "--avcodec-hw=none",        # safer decoding
    #     ])

    #     mp = inst.media_player_new()

    #     # --- Media object with same options ---
    #     media = inst.media_new(url)
    #     media.add_option(":no-audio")
    #     media.add_option(":network-caching=800")
    #     media.add_option(":file-caching=800")
    #     media.add_option(":demux=avformat")

    #     mp.set_media(media)

    #     popup.show()
    #     if sys.platform.startswith("win"):
    #         mp.set_hwnd(int(player.winId()))
    #     else:
    #         mp.set_xwindow(int(player.winId()))
    #     mp.play()

    #     print("[VIDEO] Playback started.")

    

    def _send_feedback(self, alert: dict, is_real: bool):
        """Send user feedback (👍/👎) using API contract."""
        alert_id = alert.get("alert_id")
        if not alert_id:
            print("[FEEDBACK][WARN] Missing alert_id; cannot update.")
            return

        payload = {
            "keys": {"alert_id": alert_id},
            "data": {"meta": {**(alert.get("meta") or {}), "is_real": is_real}}
        }

        url = f"{self.api.base}/api/tables/alerts"
        print(f"[FEEDBACK] PATCH {url} with {payload}")

        try:
            resp = self.api.http.patch(url, json=payload, timeout=6)
            resp.raise_for_status()
            result = resp.json()
            print(f"[FEEDBACK] ✅ Updated meta.is_real={is_real}, affected={result.get('affected_rows')}")
        except Exception as e:
            print("[FEEDBACK][ERROR]", e)
            QtWidgets.QMessageBox.warning(self, "Feedback Error", f"Failed to update feedback:\n{e}")

    
