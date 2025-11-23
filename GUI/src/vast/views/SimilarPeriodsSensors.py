from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox,
    QPushButton, QGridLayout
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import traceback


class SimilarPeriodsTab(QWidget):
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api

        # vector service internal Docker endpoint
        self.vector_base = "http://vector_service:8000"

        # ======= MAIN LAYOUT (compact) =======
        main = QVBoxLayout(self)
        main.setContentsMargins(20, 20, 20, 20)
        main.setSpacing(12)

        # ================================
        # HEADER
        # ================================
        title = QLabel("🌾 Similar Sensors Search")
        title.setStyleSheet("""
            QLabel {
                font-family: 'Inter';
                font-size: 26px;
                font-weight: 800;
                color: #1a1a1a;
                margin-bottom: 2px;
            }
        """)

        subtitle = QLabel("Find sensors with similar characteristics")
        subtitle.setStyleSheet("""
            QLabel {
                font-family: 'Inter';
                font-size: 13px;
                font-weight: 400;
                color: #6B7280;
                margin-bottom: 8px;
            }
        """)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(3)
        header_layout.addWidget(title)
        header_layout.addWidget(subtitle)
        main.addLayout(header_layout)

        # ================================
        # SENSOR SELECTOR
        # ================================
        sensor_row = QHBoxLayout()
        sensor_row.setSpacing(8)

        lbl = QLabel("Sensor:")
        lbl.setStyleSheet("font-size: 14px; font-weight: 600; color:#374151;")

        self.sensor_dropdown = QComboBox()
        self.sensor_dropdown.setMinimumWidth(230)
        self.sensor_dropdown.setStyleSheet("""
            QComboBox {
                background: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 8px;
                padding: 6px 10px;
                font-size: 13px;
                font-family: 'Inter';
            }
        """)

        self._load_sensor_list()

        sensor_row.addWidget(lbl)
        sensor_row.addWidget(self.sensor_dropdown)
        sensor_row.addStretch()
        main.addLayout(sensor_row)

        # ================================
        # COMPACT FILTER CARDS (GREEN)
        # ================================
        cards_row = QHBoxLayout()
        cards_row.setSpacing(8)

        self.card_same_status  = self._create_filter_card("Same Status",      "●")
        self.card_same_type    = self._create_filter_card("Same Type",        "●")
        self.card_same_day     = self._create_filter_card("Same Install Day", "●")

        cards_row.addWidget(self.card_same_status)
        cards_row.addWidget(self.card_same_type)
        cards_row.addWidget(self.card_same_day)
        main.addLayout(cards_row)

        # ================================
        # DATE FILTER (Compact card)
        # ================================
        time_box = QFrame()
        time_box.setStyleSheet("""
            QFrame {
                background: #ffffff;
                border-radius: 10px;
                border: 1px solid #e5e7eb;
                padding: 10px;
            }
        """)

        time_layout = QVBoxLayout(time_box)
        time_layout.setSpacing(4)

        time_label = QLabel("Date Filter:")
        time_label.setStyleSheet("font-size: 14px; font-weight:600; color:#374151;")

        self.date_dropdown = QComboBox()
        self.date_dropdown.setStyleSheet("""
            QComboBox {
                background: white;
                border: 1px solid #d1d5db;
                padding: 6px 10px;
                border-radius: 8px;
                font-size: 13px;
                font-family: 'Inter';
            }
        """)

        self.date_dropdown.addItem("— None —", None)
        self.date_dropdown.addItem("Today", "today")
        self.date_dropdown.addItem("Yesterday", "yesterday")

        weekdays = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        for w in weekdays:
            self.date_dropdown.addItem(w, w.lower())
        for w in weekdays:
            self.date_dropdown.addItem("Last " + w, "last_" + w.lower())

        time_layout.addWidget(time_label)
        time_layout.addWidget(self.date_dropdown)

        main.addWidget(time_box)

        # ================================
        # SEARCH BUTTON (compact)
        # ================================
        self.btn = QPushButton("🔍 Search")
        self.btn.setFixedHeight(40)
        self.btn.setStyleSheet("""
            QPushButton {
                background: #3B82F6;
                color: white;
                font-size: 15px;
                font-weight: 600;
                border-radius: 10px;
                font-family: 'Inter';
            }
            QPushButton:hover { background:#2563EB; }
        """)
        self.btn.clicked.connect(self._on_search)
        main.addWidget(self.btn)

        # ================================
        # RESULTS VIEW — FULL HEIGHT
        # ================================
        self.web = QWebEngineView()
        self.web.setMinimumHeight(350)   # pushes table to full size
        main.addWidget(self.web)

        self._placeholder()

        # Background like dashboard
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #F8FAFC, stop:1 #F1F5F9);
            }
        """)

    # ========= FILTER CARD (compact) =========
    def _create_filter_card(self, title, icon):
        card = QFrame()
        card.setProperty("active", False)

        card.setStyleSheet("""
            QFrame {
                background: #F0FDF4;
                border-radius: 12px;
                border: 1px solid #D1FAE5;
            }
            QFrame[active="true"] {
                border: 2px solid #10B981;
            }
        """)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("""
            QLabel {
                font-size: 22px;
                color: #10B981;
                font-weight: 900;
            }
        """)

        text_label = QLabel(title)
        text_label.setStyleSheet("""
            QLabel {
                font-size: 13px;
                font-weight: 600;
                color: #374151;
                font-family:'Inter';
            }
        """)

        layout.addWidget(icon_label)
        layout.addWidget(text_label)

        card.mousePressEvent = lambda e: self._toggle_card(card)
        return card

    def _toggle_card(self, card):
        state = not card.property("active")
        card.setProperty("active", state)
        card.style().unpolish(card)
        card.style().polish(card)
        card.update()

    # ========= PLACEHOLDER =========
    def _placeholder(self):
        self.web.setHtml("""
            <h3 style='text-align:center;margin-top:20px;color:#64748b;font-size:14px;'>
                Select filters and search for similar sensors.
            </h3>
        """)

    # ========= LOAD SENSOR LIST =========
    def _load_sensor_list(self):
        try:
            r = self.api.http.get(f"{self.api.base}/api/tables/sensors")
            sensors = r.json().get("rows", [])
            self.sensor_dropdown.addItem("-- Select Sensor --", None)

            for s in sensors:
                sid = s.get("sensor_id")
                name = s.get("sensor_name", "")
                self.sensor_dropdown.addItem(f"{sid} – {name}", sid)

        except Exception as e:
            print("Failed loading sensors:", e)

    # ========= BUILD PARAMS =========
    def _build_query_params(self):
        params = {}
        if self.card_same_status.property("active"):
            params["same_status"] = "true"
        if self.card_same_type.property("active"):
            params["same_type"] = "true"
        if self.card_same_day.property("active"):
            params["same_day"] = "true"

        selected = self.date_dropdown.currentData()
        if selected:
            params["date_filter"] = selected

        return params

    # ========= SEARCH =========
    def _on_search(self):
        sid = self.sensor_dropdown.currentData()
        if not sid:
            self.web.setHtml("<h3 style='color:red;text-align:center;'>Select a sensor.</h3>")
            return

        params = self._build_query_params()

        if not params:
            url = f"{self.vector_base}/similar_sensors/{sid}"
        else:
            q = "&".join([f"{k}={v}" for k, v in params.items()])
            url = f"{self.vector_base}/similar_sensors_advanced?sensor_id={sid}&{q}"

        try:
            data = self.api.http.get(url).json()
            self._render_results(data)
        except Exception as e:
            traceback.print_exc()
            self.web.setHtml(f"<h3 style='color:red'>Error: {e}</h3>")

    # ========= RENDER RESULTS (full-size table) =========
    def _render_results(self, data):
        sims = data.get("similar_sensors", [])

        if not sims:
            self.web.setHtml("<h3 style='text-align:center;color:#64748b;'>No results found.</h3>")
            return

        rows = ""
        for s in sims:
            status = s.get("status", "").lower()
            active = (status == "active")
            status_display = (
                "<span style='color:#059669;font-weight:700'>● ONLINE</span>"
                if active else
                "<span style='color:#DC2626;font-weight:700'>● OFFLINE</span>"
            )

            rows += f"""
                <tr style='border-bottom:1px solid #E5E7EB;'>
                    <td style='padding:10px;'>{s.get('sensor_id','—')}</td>
                    <td style='padding:10px;'>{s.get('sensor_name','—')}</td>
                    <td style='padding:10px;'>{s.get('sensor_type','—')}</td>
                    <td style='padding:10px;'>{s.get('install_date','—')}</td>
                    <td style='padding:10px;'>{status_display}</td>
                    <td style='padding:10px;'>{round(s.get('distance',0),3)}</td>
                </tr>
            """

        html = f"""
        <html><body style='font-family:Inter;padding:10px;'>

            <table style='width:100%;border-collapse:collapse;font-size:15px;'>
                <thead>
                    <tr style='background:#F8FAFC;border-bottom:2px solid #E5E7EB;'>
                        <th style='padding:10px;text-align:left;'>ID</th>
                        <th style='padding:10px;text-align:left;'>Name</th>
                        <th style='padding:10px;text-align:left;'>Type</th>
                        <th style='padding:10px;text-align:left;'>Install Date</th>
                        <th style='padding:10px;text-align:left;'>Active</th>
                        <th style='padding:10px;text-align:left;'>Distance</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>

        </body></html>
        """

        self.web.setHtml(html)
