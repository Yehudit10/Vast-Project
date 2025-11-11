import traceback
import plotly.graph_objects as go
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QTimer


class SensorDetailsTab(QWidget):
    """Sensor Details Tab – compact, clean, and fully in English."""

    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.sensor_id = None
        self.sensor_names = []

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(6)

        # --- Sensor selection area ---
        self.input_layout = QHBoxLayout()
        self.label = QLabel("Select sensor:")
        self.label.setStyleSheet("font-weight:600;font-size:12px;")

        self.sensor_dropdown = QComboBox()
        self.sensor_dropdown.setStyleSheet("""
            QComboBox {
                padding:4px 8px;
                border:1px solid #cbd5e1;
                border-radius:4px;
                font-size:12px;
                background:white;
                min-width:150px;
            }
            QComboBox:hover { border:1px solid #2563eb; }
        """)

        self.load_button = QPushButton("Show Data")
        self.load_button.setStyleSheet("""
            QPushButton {
                background:#2563eb;
                color:white;
                border:none;
                border-radius:4px;
                padding:4px 10px;
                font-size:12px;
                font-weight:600;
            }
            QPushButton:hover { background:#1d4ed8; }
        """)
        self.load_button.clicked.connect(self._on_load_clicked)

        self.input_layout.addWidget(self.label)
        self.input_layout.addWidget(self.sensor_dropdown)
        self.input_layout.addWidget(self.load_button)
        main_layout.addLayout(self.input_layout)

        # --- Web view area ---
        self.web = QWebEngineView()
        main_layout.addWidget(self.web)

        # --- Auto-refresh timer ---
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(15000)

        # Load available sensors list
        self._load_sensor_list()
        self.web.setHtml("<h3 style='text-align:center;color:#64748b;margin-top:30px;'>Please select a sensor to view details</h3>")

    # --------------------------------------------------------
    def _load_sensor_list(self):
        """Load sensor names from the API."""
        try:
            r = self.api.http.get(f"{self.api.base}/api/tables/sensors")
            data = r.json().get("rows", [])
            self.sensor_names = [s["sensor_name"] for s in data if "sensor_name" in s]
            self.sensor_dropdown.clear()
            self.sensor_dropdown.addItem("-- Select Sensor --")
            for name in self.sensor_names:
                self.sensor_dropdown.addItem(name)
        except Exception as e:
            print(f"[SensorDetailsTab] Failed to load sensors list: {e}")

    # --------------------------------------------------------
    def _on_load_clicked(self):
        """Triggered when user clicks 'Show Data'."""
        selected = self.sensor_dropdown.currentText().strip()
        if not selected or selected == "-- Select Sensor --":
            self.web.setHtml("<h4 style='text-align:center;color:#dc2626;margin-top:20px;'>Please select a sensor from the list</h4>")
            return
        self.load_sensor(selected)

    # --------------------------------------------------------
    def load_sensor(self, sensor_id: str):
        """Called when a sensor is selected manually or from the map."""
        self.sensor_id = sensor_id
        self.refresh_data()

    # --------------------------------------------------------
    def refresh_data(self):
        """Fetch data from API and refresh the dashboard."""
        if not self.sensor_id:
            return
        try:
            # Sensors
            r_sensor = self.api.http.get(f"{self.api.base}/api/tables/sensors?sensor_name={self.sensor_id}")
            sensors = r_sensor.json().get("rows", [])
            sensor_data = sensors[0] if sensors else {}

            # Logs
            r_logs = self.api.http.get(f"{self.api.base}/api/tables/event_logs_sensors?device_id={self.sensor_id}&order_by=start_ts&order_dir=desc")
            logs = r_logs.json().get("rows", [])

            # Modal anomalies
            r_modal = self.api.http.get(f"{self.api.base}/api/tables/sensors_anomalies_modal?sensor_id={self.sensor_id}&order_by=ts&order_dir=desc")
            modal = r_modal.json().get("rows", [])

            # Sensor anomalies
            r_anoms = self.api.http.get(f"{self.api.base}/api/tables/sensor_anomalies?sensor={self.sensor_id}&limit=50&order_by=ts&order_dir=desc")
            anoms = r_anoms.json().get("rows", [])

            # Active alert
            active_alert = next((a for a in logs if a.get("end_ts") is None), None)

            chart_html = self._build_plot(anoms)
            page_html = self._build_html(sensor_data, logs, modal, active_alert, chart_html)
            self.web.setHtml(page_html)
        except Exception as e:
            traceback.print_exc()
            self.web.setHtml(f"<h4 style='color:red;text-align:center;'>Error: {e}</h4>")

    # --------------------------------------------------------
    def _build_plot(self, anoms):
        """Build the Plotly chart."""
        if not anoms:
            return "<div style='text-align:center;color:#94a3b8;'>No data available for this sensor</div>"

        timestamps = [a.get("ts") for a in anoms]
        values = [a.get("value") for a in anoms]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=timestamps, y=values, mode="lines+markers",
            line=dict(color="#2563eb", width=2),
            marker=dict(size=4)
        ))
        fig.update_layout(
            template="plotly_white",
            height=240,
            margin=dict(l=20, r=20, t=20, b=20),
            xaxis_title="Timestamp",
            yaxis_title="Value",
            font=dict(family="Inter,Segoe UI,sans-serif", size=10)
        )
        return fig.to_html(include_plotlyjs="cdn", full_html=False)

    # --------------------------------------------------------
    def _build_html(self, sensor_data, logs, modal, active_alert, chart_html):
        """Generate the full HTML layout."""
        sensor_name = sensor_data.get("sensor_name", self.sensor_id)
        active_html = ""
        if active_alert:
            sev = active_alert.get("severity", "warn").capitalize()
            issue = active_alert.get("issue_type", "Unknown")
            started = active_alert.get("start_ts", "")[:19]
            active_html = f"""
            <div class='alert-banner'>
                Active Alert: <b>{issue}</b> | Severity: <b>{sev}</b> | Started: {started}
            </div>
            """

        combined = []
        for l in logs:
            combined.append({
                "time": l.get("start_ts"),
                "issue": l.get("issue_type"),
                "severity": l.get("severity"),
                "source": "event_logs_sensors"
            })
        for m in modal:
            is_anomaly = m.get("anomaly") not in (0, "0", False, "false", None)
            combined.append({
                "time": m.get("ts"),
                "issue": "Model anomaly detected" if is_anomaly else "Model normal",
                "severity": "critical" if is_anomaly else "info",
                "source": "sensors_anomalies_modal"
            })
        combined.sort(key=lambda x: x.get("time") or "", reverse=True)

        rows = "".join([
            f"<tr><td>{r['time'][:19]}</td><td>{r['issue']}</td>"
            f"<td class='sev-{r['severity']}'>{r['severity'].capitalize()}</td><td>{r['source']}</td></tr>"
            for r in combined
        ]) or "<tr><td colspan='4' style='text-align:center;color:#94a3b8;'>No alerts found</td></tr>"

        return f"""
<!DOCTYPE html>
<html lang='en'>
<head><meta charset='UTF-8'>
<style>
body {{font-family:'Inter','Segoe UI',sans-serif;margin:0;padding:10px 14px;background:#f9fafb;color:#0f172a;font-size:0.85rem;}}
h1 {{font-size:1.1rem;font-weight:800;margin:0 0 8px 0;}}
.alert-banner {{background:#fee2e2;border:1px solid #dc2626;color:#b91c1c;border-radius:6px;
padding:6px 10px;margin-bottom:10px;font-weight:600;font-size:0.8rem;}}
.card {{background:white;border:1px solid #e2e8f0;border-radius:8px;padding:8px 10px;
margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,0.02);}}
.card h2 {{font-size:0.9rem;font-weight:700;color:#1e293b;margin:0 0 6px 0;}}
table {{width:100%;border-collapse:collapse;font-size:0.8rem;}}
thead {{background:#f1f5f9;}}
th,td {{padding:6px 8px;text-align:left;border-bottom:1px solid #e2e8f0;}}
th {{color:#334155;font-weight:600;}}
tr:hover td {{background:#f9fafb;}}
.sev-critical {{color:#dc2626;font-weight:700;}}
.sev-info {{color:#2563eb;}}
.sev-warn {{color:#f97316;font-weight:600;}}
</style></head>
<body>
<h1>Sensor: {sensor_name}</h1>
{active_html}
<div class='card'><h2>Sensor Readings</h2>{chart_html}</div>
<div class='card'><h2>Alerts History</h2>
<table><thead><tr><th>Time</th><th>Issue</th><th>Severity</th><th>Source</th></tr></thead>
<tbody>{rows}</tbody></table></div>
</body></html>
"""
