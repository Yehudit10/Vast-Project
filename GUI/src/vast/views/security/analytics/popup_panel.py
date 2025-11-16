from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QGridLayout, QSizePolicy
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtCore import Qt, QMargins
from PyQt6.QtCharts import (
    QChart, QChartView, QBarSeries, QBarSet, QBarCategoryAxis,
    QValueAxis, QLineSeries, QCategoryAxis
)
from PyQt6.QtCharts import QPieSeries  # local import to avoid top clutter

class AnalyticsPanel(QWidget):
    """Fixed right-side analytics dashboard panel (2×2 grid layout)."""

    def __init__(self, title: str, data: dict, parent: QWidget | None = None):
        super().__init__(parent)

        # ─────────────────────────────
        # Palette
        # ─────────────────────────────
        self.green = "#10b981"
        self.black = "#111827"
        self.gray = "#6b7280"
        self.bg_light = "#f9fafb"

        # ─────────────────────────────
        # Layout
        # ─────────────────────────────
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Title
        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(f"font-size:20pt;font-weight:700;color:{self.green};")
        layout.addWidget(self.title_label)

        # 2×2 grid
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
        layout.addLayout(self.grid, stretch=1)

        # Populate initial data
        self._populate(data)

    # ─────────────────────────────
    def update_data(self, title: str, data: dict):
        self.title_label.setText(title)
        self._populate(data)

    # ─────────────────────────────
    def _populate(self, data: dict):
        # Clear old widgets
        for i in reversed(range(self.grid.count())):
            item = self.grid.itemAt(i).widget()
            if item:
                item.setParent(None)

        # Create 4 panels
        # bar_panel = self._section("Alerts by Type", self._make_bar_chart(data.get("alerts_by_type", {})))
        bar_panel = self._section("Alerts by Type", self._make_pie_chart(data.get("alerts_by_type", {})))

        line_panel = self._section("Alerts per Month", self._make_line_chart(data.get("alerts_per_month", {})))
        summary_panel = self._section("Summary", self._make_summary_panel(
            data.get("total_alerts", 0),
            data.get("avg_severity", 0),
            data.get("avg_confidence", 0)
        ))
        # details_panel = self._section("Details", self._placeholder("More analytics coming soon..."))
        details_panel = self._section(
    "Avg Alert Duration (min)",
    self._make_bar_chart(data.get("avg_duration_per_type", {}))
)

        # Add to 2×2 grid
        self.grid.addWidget(bar_panel, 0, 0)
        self.grid.addWidget(line_panel, 0, 1)
        self.grid.addWidget(summary_panel, 1, 0)
        self.grid.addWidget(details_panel, 1, 1)

        # Equal stretch
        self.grid.setRowStretch(0, 1)
        self.grid.setRowStretch(1, 1)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1)

    # ─────────────────────────────
    def _section(self, header_text: str, widget: QWidget):
        section = QFrame()
        section.setStyleSheet(f"QFrame {{ background:{self.bg_light}; border-radius:10px; }}")
        vbox = QVBoxLayout(section)
        vbox.setContentsMargins(8, 8, 8, 8)
        vbox.setSpacing(6)
        header = QLabel(header_text)
        header.setStyleSheet(f"color:{self.gray};font-weight:600;font-size:11pt;")
        vbox.addWidget(header)
        vbox.addWidget(widget)
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        return section

    # ─────────────────────────────
    # 🔹 Helper: compute nice Y-axis
    # ─────────────────────────────
    def _setup_nice_y_axis(self, data_values):
        axis_y = QValueAxis()

        if not data_values:
            axis_y.setRange(0, 3)
            axis_y.setTickInterval(1)
            return axis_y

        max_val = max(data_values)
        upper = max_val * 1.2
        if upper <= 3:
            upper = 3.0

        # Pick a "nice" step: 1, 2, 5, 10, 20, 50, ...
        nice_steps = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000]
        step = next((s for s in nice_steps if upper / s <= 6), 1000)
        upper = (int(upper / step) + 1) * step

        axis_y.setRange(0, upper)
        axis_y.setTickInterval(step)
        axis_y.setLabelFormat("%.1f" if any(v < 10 for v in data_values) else "%.0f")
        # axis_y.setLabelFormat("%.0f")
        axis_y.setMinorTickCount(0)
        return axis_y

    # ─────────────────────────────
    def _make_bar_chart(self, data: dict):
        if not data:
            return self._placeholder("No data")

        chart = QChart()
        chart.legend().setVisible(False)
        chart.setBackgroundVisible(False)
        chart.setMargins(QMargins(8, 8, 8, 8))

        # Bar series
        bar_set = QBarSet("Alerts")
        for v in data.values():
            bar_set.append(float(v))
        series = QBarSeries()
        series.append(bar_set)
        chart.addSeries(series)

        # X-axis
        axis_x = QBarCategoryAxis()
        axis_x.append(list(data.keys()))

        # Y-axis (nice scaling)
        axis_y = self._setup_nice_y_axis(list(data.values()))

        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

        bar_set.setColor(QColor(self.green))

        # Chart view
        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(200)
        view.setStyleSheet("background:transparent;")
        return view
        # ─────────────────────────────
    def _make_pie_chart(self, data: dict):
        """Create a pie chart (e.g., Alerts by Type) with distinct green shades."""
        if not data:
            return self._placeholder("No data")

        chart = QChart()
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        chart.setBackgroundVisible(False)
        chart.setMargins(QMargins(8, 8, 8, 8))

        # Pie series
        series = QPieSeries()
        total = sum(data.values()) or 1

        # Define a clearer set of green shades (light → dark)
        green_shades = [
            QColor("#A7F3D0"),  # light mint
            QColor("#6EE7B7"),  # medium mint
            QColor("#34D399"),  # base green
            QColor("#10B981"),  # emerald
            QColor("#059669"),  # dark green
            QColor("#047857"),  # deeper green
        ]

        max_val = max(data.values()) if data else 0

        for i, (key, val) in enumerate(data.items()):
            slice_ = series.append(f"{key} ({val})", float(val))
            slice_.setLabelVisible(True)

            # Pick shade cyclically
            color = green_shades[i % len(green_shades)]
            slice_.setBrush(color)
            slice_.setPen(QColor("#ffffff"))  # white borders
            slice_.setLabelColor(QColor(self.black))

            # Slightly explode only the largest slice
            # if val == max_val:
            #     slice_.setExploded(True)
            #     slice_.setLabelFont(self.font())

        chart.addSeries(series)
        chart.setAnimationOptions(QChart.AnimationOption.AllAnimations)

        # Chart view
        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(200)
        view.setStyleSheet("background:transparent;")
        return view



    # ─────────────────────────────
    def _make_line_chart(self, data: dict):
        if not data:
            return self._placeholder("No data")

        sorted_items = sorted(data.items())
        chart = QChart()
        chart.legend().setVisible(False)
        chart.setBackgroundVisible(False)
        chart.setMargins(QMargins(8, 8, 8, 8))

        # Create line series
        series = QLineSeries()
        for i, (_, val) in enumerate(sorted_items):
            series.append(i, float(val))
        pen = series.pen()
        pen.setColor(QColor(self.green))
        pen.setWidth(3)
        series.setPen(pen)
        chart.addSeries(series)

        # X-axis (months)
        axis_x = QCategoryAxis()
        for i, (month, _) in enumerate(sorted_items):
            axis_x.append(month, i)

        # Y-axis (nice scaling)
        axis_y = self._setup_nice_y_axis(list(data.values()))

        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)

        view = QChartView(chart)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setMinimumHeight(200)
        view.setStyleSheet("background:transparent;")
        return view

    # ─────────────────────────────
    def _make_summary_panel(self, total, avg_sev, avg_conf):
        label = QLabel(
            f"<b>Total Alerts:</b> {total}<br>"
            f"<b>Avg Severity:</b> {avg_sev:.2f}<br>"
            f"<b>Avg Confidence:</b> {avg_conf:.2f}"
        )
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(f"font-size:12pt;color:{self.black};")
        return label

    # ─────────────────────────────
    def _placeholder(self, text: str):
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color:#9ca3af;font-size:10pt;font-style:italic;")
        return lbl
