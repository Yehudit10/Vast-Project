from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QGridLayout, QFrame, QDialog, QDialogButtonBox,
    QFormLayout, QComboBox
)
from PyQt6.QtCore import Qt, QTimer
import traceback


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

        # ← NEW: show sensor_id
        sensor_id = self.data.get("sensor_id", "N/A")
        id_lbl = QLabel(f"ID: {sensor_id}")
        id_lbl.setStyleSheet("color:#777; font-size:12px;")
        layout.addWidget(id_lbl)

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

        self.setFixedSize(230, 120)


# ============================================================
#   ALERT DETAILS DIALOG
# ============================================================
class AlertDialog(QDialog):
    def __init__(self, sensor):
        super().__init__()
        self.setWindowTitle(f"Sensor Details – {sensor.get('sensor_name')}")
        self.setMinimumSize(520, 450)

        layout = QVBoxLayout(self)

        # ← NEW: richer sensor details
        sensor_details = f"""
        <b>Name:</b> {sensor.get('sensor_name')}<br>
        <b>ID:</b> {sensor.get('sensor_id')}<br>
        <b>Type:</b> {sensor.get('sensor_type')}<br>
        <b>Status:</b> {sensor.get('status', 'Unknown')}<br>
        <b>Latitude:</b> {sensor.get('lat', 'N/A')}<br>
        <b>Longitude:</b> {sensor.get('lon', 'N/A')}<br>
        """
        header = QLabel(sensor_details)
        header.setWordWrap(True)
        layout.addWidget(header)

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

                form = QFormLayout(card)
                start = a.get("start_ts", "")[:19]
                end = a.get("end_ts", "")
                form.addRow("Start:", QLabel(start))
                form.addRow("End:", QLabel(end if end else "[ACTIVE]"))
                form.addRow("Issue:", QLabel(a.get("issue_type", "")))
                form.addRow("Severity:", QLabel(a.get("severity", "")))

                details = a.get("details", {})
                for k, v in details.items():
                    form.addRow(f"{k.title()}:", QLabel(str(v)))

                body_layout.addWidget(card)
        else:
            body_layout.addWidget(QLabel("No alerts."))

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

        # ← REMOVED refresh button completely

        main_layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.container)
        main_layout.addWidget(self.scroll)

        self.setLayout(main_layout)

    # ------------------------------------------------------------
    def load_sensors(self):
        try:
            res_sensors = self.api.http.get(f"{self.api.base}/api/tables/sensors").json()
            res_anoms = self.api.http.get(f"{self.api.base}/api/tables/sensors_anomalies_modal").json()
            res_logs = self.api.http.get(f"{self.api.base}/api/tables/event_logs_sensors").json()

            sensors = res_sensors.get("rows", [])
            anomalies = res_anoms.get("rows", [])
            alerts = res_logs.get("rows", [])

        except:
            traceback.print_exc()
            return

        # --------------- map anomalies ---------------
        anomaly_latest = {}
        for a in anomalies:
            sid = a.get("sensor_id")
            if not sid:
                continue
            prev = anomaly_latest.get(sid)
            if prev is None or a.get("ts", "") > prev.get("ts", ""):
                anomaly_latest[sid] = a

        # --------------- map alerts ---------------
        alerts_by_sensor = {}
        for alert in alerts:
            dev = alert.get("device_id")
            if not dev:
                continue
            if alert.get("end_ts"):
                continue
            alerts_by_sensor.setdefault(dev, []).append(alert)

        # --------------- merge ---------------
        merged = []
        for s in sensors:
            sensor_id = s.get("sensor_id")
            name = s.get("sensor_name")
            s_type = s.get("sensor_type")

            alerts_for_s = alerts_by_sensor.get(name, [])
            active = [a for a in alerts_for_s if not a.get("end_ts")]

            if active:
                latest = sorted(active, key=lambda x: x.get("start_ts", ""), reverse=True)[0]
                sev_alert = latest.get("severity", "info").lower()
                issue_alert = latest.get("issue_type", "")
            else:
                sev_alert = "info"
                issue_alert = None

            anom = anomaly_latest.get(sensor_id)
            if anom and anom.get("anomaly", 0) > 0:
                sev_anom = "error"
                issue_anom = "Anomaly detected"
            else:
                sev_anom = "info"
                issue_anom = None

            sev_final = sev_alert
            issue_final = issue_alert or "No active alerts"
            if SEVERITY_RANK[sev_anom] > SEVERITY_RANK[sev_alert]:
                sev_final = sev_anom
                issue_final = issue_anom

            all_alerts = alerts_for_s.copy()
            if anom:
                all_alerts.append({
                    "start_ts": anom.get("ts"),
                    "severity": sev_anom,
                    "issue_type": "anomaly_modal",
                    "details": {"anomaly": anom.get("anomaly")}
                })

            merged.append({
                "sensor_id": sensor_id,
                "sensor_name": name,
                "sensor_type": s_type,
                "Issue": issue_final,
                "Severity": sev_final,
                "All Alerts": all_alerts,
                "status": s.get("status"),
                "lat": s.get("lat"),
                "lon": s.get("lon"),
            })

        self.all_sensors = merged
        self._apply_filters()

    # ------------------------------------------------------------
    def _render_cards(self, sensors):
        for i in reversed(range(self.grid.count())):
            w = self.grid.itemAt(i).widget()
            if w:
                w.setParent(None)

        if not sensors:
            lbl = QLabel("No sensors found")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid.addWidget(lbl, 0, 0)
            return

        cols = 3
        for i, s in enumerate(sensors):
            card = SensorCard(s, self._show_alert_history)
            r, c = divmod(i, cols)
            self.grid.addWidget(card, r, c)

    # ------------------------------------------------------------
    def _apply_filters(self):
        text = self.search_box.text().lower().strip()
        filt = self.filter_box.currentText().lower()

        filtered = []
        for s in self.all_sensors:
            name = str(s.get("sensor_name", "")).lower()
            t = str(s.get("sensor_type", "")).lower()
            sev = s.get("Severity", "").lower()

            if text and text not in name and text not in t:
                continue
            if filt != "all" and filt not in sev:
                continue
            filtered.append(s)

        self._render_cards(filtered)

    # ------------------------------------------------------------
    def _show_alert_history(self, sensor):
        dlg = AlertDialog(sensor)
        dlg.exec()
