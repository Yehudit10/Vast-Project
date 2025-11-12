from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QScrollArea, QGridLayout, QFrame, QDialog, QDialogButtonBox, QFormLayout, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, QDateTime
import traceback


# ============================================================
#   CONSTANTS
# ============================================================
SEVERITY_RANK = {
    "info": 0,
    "ok": 0,
    "normal": 0,
    "warn": 1,
    "warning": 1,
    "error": 2,
    "critical": 3,
}


# ============================================================
#   SENSOR CARD
# ============================================================
class SensorCard(QFrame):
    """Modern compact sensor card"""
    def __init__(self, sensor_data: dict, on_click):
        super().__init__()
        self.data = sensor_data
        self.on_click = on_click
        self.setObjectName("card")
        self._build_ui()
        self.mousePressEvent = self._on_click

    def _on_click(self, event):
        self.on_click(self.data)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(5)
        layout.setContentsMargins(12, 12, 12, 10)

        title = QLabel(self.data.get("sensor_name", "Unknown Sensor"))
        title.setStyleSheet("font-weight:600; font-size:15px; color:#111;")
        layout.addWidget(title)

        stype = QLabel(f"Type: {self.data.get('sensor_type', 'N/A')}")
        stype.setStyleSheet("color:#555; font-size:12px;")
        layout.addWidget(stype)

        issue = QLabel(f"Issue: {self.data.get('Issue', 'No alerts')}")
        issue.setStyleSheet("font-size:12px; color:#444;")
        layout.addWidget(issue)

        layout.addStretch()

        sev = self.data.get("Severity", "info").lower()
        sev_label = QLabel(sev.capitalize())
        sev_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sev_label.setFixedHeight(20)

        if sev == "info":
            sev_label.setStyleSheet("background-color:#D9FAD3; color:#1B5E20; border-radius:6px; font-weight:600;")
        elif sev in ("warn", "warning"):
            sev_label.setStyleSheet("background-color:#FFF5BA; color:#8B8000; border-radius:6px; font-weight:600;")
        elif sev in ("error", "critical"):
            sev_label.setStyleSheet("background-color:#FFD5D5; color:#B71C1C; border-radius:6px; font-weight:600;")
        else:
            sev_label.setStyleSheet("background-color:#EEE; color:#333; border-radius:6px; font-weight:600;")

        layout.addWidget(sev_label)

        self.setFixedSize(230, 110)
        self.setStyleSheet("""
            QFrame#card {
                border-radius: 12px;
                border: 1px solid #DDD;
                background-color: #FFFFFF;
                transition: 200ms;
            }
            QFrame#card:hover {
                border: 1px solid #0078D7;
                background-color: #F6F9FF;
            }
        """)


# ============================================================
#   ALERT DETAILS DIALOG
# ============================================================
class AlertDialog(QDialog):
    def __init__(self, sensor):
        super().__init__()
        self.setWindowTitle(f"Alert Details – {sensor.get('sensor_name')}")
        self.setMinimumSize(480, 360)
        self.setStyleSheet("""
            QDialog { background-color: #FAFAFA; border-radius: 10px; }
            QLabel { font-size: 13px; color: #222; }
            QPushButton {
                background-color: #0078D7; color: white; border-radius: 6px;
                padding: 6px 12px; font-weight: 600;
            }
            QPushButton:hover { background-color: #005FA3; }
        """)

        layout = QVBoxLayout(self)
        title = QLabel(f"<b>Sensor:</b> {sensor.get('sensor_name')}<br>"
                       f"<b>Type:</b> {sensor.get('sensor_type')}<br>"
                       f"<b>Current Issue:</b> {sensor.get('Issue')}<br>"
                       f"<b>Severity:</b> {sensor.get('Severity')}<br>")
        title.setWordWrap(True)
        layout.addWidget(title)

        alerts = sensor.get("All Alerts", [])
        layout.addSpacing(10)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(8)

        if alerts:
            for a in sorted(alerts, key=lambda x: x.get("start_ts", ""), reverse=True):
                card = QFrame()
                severity = a.get("severity", "info")
                border_color = {
                    "critical": "#FF4444",
                    "error": "#FF8800",
                    "warn": "#FFCC00",
                }.get(severity, "#44AA44")

                card.setStyleSheet(f"""
                    QFrame {{
                        border-radius: 8px;
                        border: 2px solid {border_color};
                        background-color: #FFF;
                        padding: 6px;
                        margin: 2px;
                    }}
                """)
                card_layout = QFormLayout(card)
                start_time = a.get("start_ts", "")[:19] if a.get("start_ts") else ""
                end_time = a.get("end_ts")
                end_display = end_time[:19] if end_time else "[ACTIVE]"
                card_layout.addRow("Start Time:", QLabel(start_time))
                card_layout.addRow("End Time:", QLabel(end_display))
                card_layout.addRow("Issue:", QLabel(a.get("issue_type", "")))
                card_layout.addRow("Severity:", QLabel(a.get("severity", "")))
                details = a.get("details", {})
                if details:
                    for key, val in details.items():
                        card_layout.addRow(f"{key.title()}:", QLabel(str(val)))
                body_layout.addWidget(card)
        else:
            body_layout.addWidget(QLabel("No previous alerts or anomalies."))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout.addWidget(scroll)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btns.accepted.connect(self.accept)
        layout.addWidget(btns)


# ============================================================
#   MAIN VIEW
# ============================================================
class SensorsView(QWidget):
    """Unified sensors view merging anomalies + alerts"""
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.all_sensors = []
        self._build_ui()
        self.load_sensors()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.load_sensors)
        self.timer.start(30000)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(10)

        # ---------- Header ----------
        header = QHBoxLayout()
        title = QLabel("🌡️ Unified Sensor Alerts Dashboard")
        title.setStyleSheet("font-size:22px; font-weight:700; color:#111;")
        header.addWidget(title)
        header.addStretch()

        self.filter_box = QComboBox()
        self.filter_box.addItems(["All", "Info", "Warning", "Error", "Critical"])
        self.filter_box.currentTextChanged.connect(self._apply_filters)
        header.addWidget(self.filter_box)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search sensors...")
        self.search_box.textChanged.connect(self._apply_filters)
        self.search_box.setFixedWidth(220)
        header.addWidget(self.search_box)

        self.refresh_btn = QPushButton("⟳ Refresh")
        self.refresh_btn.clicked.connect(self.load_sensors)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D7;
                color: white;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #005FA3; }
        """)
        header.addWidget(self.refresh_btn)
        main_layout.addLayout(header)

        # ---------- Scroll with cards ----------
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)
        self.setLayout(main_layout)

    # ----------------------------
    def load_sensors(self):
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("⟳ Loading...")

        try:
            res_sensors = self.api.http.get(f"{self.api.base}/api/tables/sensors", timeout=10).json()
            res_anoms = self.api.http.get(f"{self.api.base}/api/tables/sensors_anomalies_modal", timeout=10).json()
            res_logs = self.api.http.get(f"{self.api.base}/api/tables/event_logs_sensors", timeout=10).json()
            sensors = res_sensors.get("rows", [])
            anomalies = res_anoms.get("rows", [])
            alerts = res_logs.get("rows", [])
        except Exception as e:
            traceback.print_exc()
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("↻ Refresh")
            return

        # map anomalies by sensor
        anomaly_latest = {}
        for a in anomalies:
            sid = a.get("sensor_id")
            if not sid:
                continue
            prev = anomaly_latest.get(sid)
            if prev is None or a.get("ts", "") > prev.get("ts", ""):
                anomaly_latest[sid] = a

        # map alerts (event_logs_sensors)
        alerts_by_sensor = {}
        for alert in alerts:
            dev_id = alert.get("device_id")
            if not dev_id:
                continue
            if alert.get("end_ts"):
                continue  # closed alert
            alerts_by_sensor.setdefault(dev_id, []).append(alert)

        merged = []
        for s in sensors:
            sid = s.get("sensor_name")
            s_type = s.get("sensor_type", "Unknown")

            alerts_for_s = alerts_by_sensor.get(sid, [])
            active_alerts = [a for a in alerts_for_s if not a.get("end_ts")]

            # determine severity from alerts
            if active_alerts:
                latest_alert = sorted(active_alerts, key=lambda x: x.get("start_ts", ""), reverse=True)[0]
                sev_alert = latest_alert.get("severity", "info").lower()
                issue_alert = latest_alert.get("issue_type", "alert")
            else:
                sev_alert = "info"
                issue_alert = None

            # determine severity from anomalies
            anom = anomaly_latest.get(sid)
            if anom and anom.get("anomaly", 0) > 0:
                sev_anom = "error"  # you can adjust mapping of numeric to severity
                issue_anom = "Anomaly detected"
            else:
                sev_anom = "info"
                issue_anom = None

            # pick the most severe
            sev_final = sev_alert
            issue_final = issue_alert or "No active alerts"
            if SEVERITY_RANK[sev_anom] > SEVERITY_RANK[sev_alert]:
                sev_final = sev_anom
                issue_final = issue_anom

            all_alerts = alerts_for_s.copy()
            if anom:
                all_alerts.append({
                    "issue_type": "anomaly_modal",
                    "severity": sev_anom,
                    "start_ts": anom.get("ts"),
                    "details": {"anomaly": anom.get("anomaly")}
                })

            merged.append({
                "sensor_name": sid,
                "sensor_type": s_type,
                "Issue": issue_final,
                "Severity": sev_final,
                "All Alerts": all_alerts
            })

        self.all_sensors = merged
        self._apply_filters()
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("↻ Refresh")

    # ----------------------------
    def _render_cards(self, sensors):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        if not sensors:
            no_data = QLabel("No sensors found matching your criteria")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data.setStyleSheet("color:#666; font-size:16px; padding:40px;")
            self.grid.addWidget(no_data, 0, 0, 1, 3)
            return

        cols = 3
        for idx, s in enumerate(sensors):
            card = SensorCard(s, self._show_alert_history)
            r, c = divmod(idx, cols)
            self.grid.addWidget(card, r, c, Qt.AlignmentFlag.AlignTop)

    # ----------------------------
    def _apply_filters(self):
        text = self.search_box.text().strip().lower()
        sev_filter = self.filter_box.currentText().lower()
        filtered = []

        for s in self.all_sensors:
            sid = str(s.get("sensor_name", "")).lower()
            stype = str(s.get("sensor_type", "")).lower()
            sev = s.get("Severity", "").lower()

            if text and text not in sid and text not in stype:
                continue
            if sev_filter != "all" and sev_filter not in sev:
                continue
            filtered.append(s)

        self._render_cards(filtered)

    # ----------------------------
    def _show_alert_history(self, sensor):
        dlg = AlertDialog(sensor)
        dlg.exec()
