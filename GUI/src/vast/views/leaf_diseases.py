# leaf_diseases.py (compact, fixed + Grafana integration)
# UI: English, Comments: English, 4 spaces indent.

from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable, Optional, Tuple

from PyQt6.QtCore import QDate, QTimer, Qt, QPointF, pyqtSignal, QUrl
from PyQt6.QtGui import QPainter, QPen, QColor
from PyQt6.QtWidgets import (
    QCalendarWidget, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget, QDateEdit, QProgressBar  
)
from PyQt6.QtWebEngineWidgets import QWebEngineView

from dashboard_api import DashboardApi

# ──────────────────────────────
# Small utils
# ──────────────────────────────

def _color_for_pct(pct: float) -> str:
    """Traffic-light color by percentage."""
    return "#22c55e" if pct < 20 else ("#f59e0b" if pct <= 50 else "#ef4444")

def _is_sick(v) -> bool:
    """Normalize truthy sick flags from DB."""
    return v in [True, "true", "t", "1", 1, "yes", "y"]

def _ts_to_date(ts: str) -> Optional[datetime.date]:
    """Parse ISO ts (supports 'Z')."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except Exception:
        return None

def _json_rows(payload) -> list:
    """Accept list or any common envelope {data/items/rows/...}."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "results", "items", "records", "rows"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
    return []

def _clear_layout(layout) -> None:
    """Remove all widgets from a layout."""
    while layout.count():
        itm = layout.takeAt(0)
        w = itm.widget()
        if w:
            w.deleteLater()

# Styles (one place)
APP_STYLES = """
QWidget {
  background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0a0f1f, stop:1 #060913);
  color: #e5e7eb; font-family: ui-sans-serif, system-ui, 'Segoe UI', Roboto, sans-serif;
}
QScrollArea { border: none; background: transparent; }
QLabel { color: #e5e7eb; background: transparent; }

QPushButton {
  background: #0f1a33; border: 1px solid #1f2b49; border-radius: 12px;
  color: #e5e7eb; padding: 10px 20px; font-weight: 600; font-size: 13px;
}
QPushButton:hover { background: #1a2a4a; border: 1px solid #3d5a8f; }
QPushButton:pressed { background: #0a1220; }

QDateEdit { background: transparent; border: none; color: #e5e7eb; padding: 6px 10px; font-size: 13px; }
QDateEdit::drop-down { border: none; background: transparent; width: 20px; }

QFrame.card {
  background: qradialgradient(cx:0.9, cy:-0.1, radius:1.2, fx:0.9, fy:-0.1,
    stop:0 #243b55, stop:0.35 #111827, stop:1 #0b1220);
  border: 1px solid #1f2937; border-radius: 16px; padding: 16px;
}

/* nicer disease chips */
.Tag {
  background: #0b1220; border: 1px solid #1f2937;
  border-radius: 999px; padding: 6px 12px; font-size: 12px;
}
.Tag:hover { border-color: #334155; box-shadow: 0 0 0 2px rgba(99,102,241,.15); }

/* progress bars */
QProgressBar {
  background: #0b1220; border: 1px solid #1f2937; border-radius: 999px;
  min-height: 14px; max-height: 14px; text-align: center;
}
QProgressBar::chunk {
  border-radius: 999px;
}
"""


# ──────────────────────────────
# Clickables
# ──────────────────────────────

class ClickableRow(QFrame):
    clicked = pyqtSignal(str)
    def __init__(self, key: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.key = key
        self.setStyleSheet("QFrame { background: transparent; }")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
    def mousePressEvent(self, e):  # noqa: N802
        self.clicked.emit(self.key)
        super().mousePressEvent(e)

ClickableTag = ClickableRow  # identical behavior

# ──────────────────────────────
# Tiny sparkline
# ──────────────────────────────

class TrendSparkline(QFrame):
    """Minimal line chart for percentages (0..100)."""
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._series: list[float] = []
        self.setMinimumHeight(160)
        self.setStyleSheet("QFrame { background: #0b1220; border: 1px solid #1f2937; border-radius: 16px; }")
    def set_series(self, values: Iterable[float]) -> None:
        self._series = list(values) if values else []
        self.update()
    def paintEvent(self, _):  # noqa: N802
        super().paintEvent(_)
        if not self._series:
            return
        p = QPainter(self); p.setRenderHints(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        L, T, R, B = 16, 12, 16, 20
        cw, ch = max(1, w - L - R), max(1, h - T - B)
        pen_axis = QPen(QColor("#1f2937")); pen_axis.setWidth(1); p.setPen(pen_axis)
        p.drawLine(L, h - B, w - R, h - B); p.drawLine(L, T, L, h - B)
        n = len(self._series); dx = cw / max(1, n - 1); pts = []
        for i, val in enumerate(self._series):
            v = max(0.0, min(100.0, float(val)))
            pts.append(QPointF(L + i * dx, T + (100.0 - v) / 100.0 * ch))
        pen_line = QPen(QColor("#6366f1")); pen_line.setWidth(2); p.setPen(pen_line)
        for i in range(1, len(pts)): p.drawLine(pts[i - 1], pts[i])
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#6366f1"))
        for idx in (0, len(pts) - 1): p.drawEllipse(pts[idx], 3.5, 3.5)

# ──────────────────────────────
# Date range dialog
# ──────────────────────────────

class DateRangeDialog(QDialog):
    """Two calendars (From/To) + clear/today/OK/Cancel."""
    def __init__(self, parent: Optional[QWidget] = None, start: Optional[QDate] = None, end: Optional[QDate] = None):
        super().__init__(parent)
        self.setWindowTitle("Select Date Range")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet("""
            QDialog { background: #0b1220; color: #e5e7eb; }
            QLabel { background: transparent; color: #e5e7eb; }
            QCalendarWidget QWidget { background: transparent; color: #e5e7eb; }
            QCalendarWidget QAbstractItemView { selection-background-color: #1e3a5f; }
            QDialogButtonBox QPushButton {
                background: #0f1a33; border: 1px solid #1f2b49; border-radius: 8px;
                color: #e5e7eb; padding: 6px 12px; font-weight: 600;
            }
            QDialogButtonBox QPushButton:hover { background: #1a2a4a; border-color: #3d5a8f; }
        """)
        main = QVBoxLayout(self); row = QHBoxLayout(); main.addLayout(row)
        min_allowed, max_allowed = QDate(2000, 1, 1), QDate(2100, 12, 31)

        def _calendar(lbl: str) -> QCalendarWidget:
            box = QVBoxLayout(); box.addWidget(QLabel(lbl))
            cal = QCalendarWidget(self)
            cal.setNavigationBarVisible(True); cal.setGridVisible(True)
            cal.setMinimumDate(min_allowed); cal.setMaximumDate(max_allowed)
            box.addWidget(cal); return box, cal

        left_box, self.cal_from = _calendar("From Date")
        right_box, self.cal_to = _calendar("To Date")
        row.addLayout(left_box); row.addItem(QSpacerItem(16, 1, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)); row.addLayout(right_box)
        today = QDate.currentDate(); self.cal_from.setSelectedDate(start or today.addDays(-7)); self.cal_to.setSelectedDate(end or today)
        buttons = QDialogButtonBox(self)
        self._btn_clear = buttons.addButton("Clear", QDialogButtonBox.ButtonRole.ActionRole)
        self._btn_today = buttons.addButton("Today", QDialogButtonBox.ButtonRole.ActionRole)
        buttons.addButton(QDialogButtonBox.StandardButton.Ok); buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self._btn_clear.clicked.connect(self._on_clear); self._btn_today.clicked.connect(self._on_today)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        main.addWidget(buttons)

    def _on_today(self): t = QDate.currentDate(); self.cal_from.setSelectedDate(t); self.cal_to.setSelectedDate(t)
    def _on_clear(self): self.cal_from.setSelectedDate(QDate()); self.cal_to.setSelectedDate(QDate())

    def selectedRange(self) -> Tuple[Optional[QDate], Optional[QDate]]:
        f, t = self.cal_from.selectedDate(), self.cal_to.selectedDate()
        if not f.isValid() or not t.isValid(): return None, None
        return (t, f) if f > t else (f, t)

# ──────────────────────────────
# Main View
# ──────────────────────────────

class LeafDiseaseView(QWidget):
    """
    Compact dashboard: date filtering, top devices, top diseases,
    device details (per-disease % of total device images).
    When clicking on disease or device, shows details below inline.
    """

    def __init__(self, api: DashboardApi, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.api = api
        self._raw: list[dict] = []
        self._types: dict[str, str] = {}  # { "1": "Blight", ... }
        self._filters_timer = QTimer(self); self._filters_timer.setSingleShot(True)
        self._filters_timer.setInterval(250); self._filters_timer.timeout.connect(self._apply_filters_and_update)
        self._setup_ui()
        self._load_types(); self._load_reports()

    # ───────── UI / build ─────────

    def _setup_ui(self) -> None:
        self.setStyleSheet(APP_STYLES)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget(); main = QVBoxLayout(container); main.setSpacing(20); main.setContentsMargins(24, 24, 24, 24)
        
        # Top section: header, controls, KPIs, cards
        main.addWidget(self._header())
        main.addWidget(self._controls())
        main.addWidget(self._kpis())
        main.addWidget(self._cards())

        # Details section (shown below when clicking)
        self.device_card = self._device_details_card()
        self.device_card.setVisible(False)
        main.addWidget(self.device_card)
        
        self.grafana_card = self._grafana_details_card()
        self.grafana_card.setVisible(False)
        main.addWidget(self.grafana_card)

        main.addStretch()
        scroll.setWidget(container)
        wrap = QVBoxLayout(self); wrap.setContentsMargins(0, 0, 0, 0); wrap.addWidget(scroll)

    def _header(self) -> QWidget:
        frame = QFrame(); h = QHBoxLayout(frame)
        h.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Field Status: Report")
        title.setStyleSheet("font-size: 22px; font-weight: 700; letter-spacing: 0.3px;")
        btn = QPushButton("🔄 Refresh"); btn.clicked.connect(self._refresh)
        h.addWidget(title); h.addStretch(); h.addWidget(btn); return frame

    def _refresh(self): self._load_types(); self._load_reports()

    def _controls(self) -> QWidget:
        box = QFrame(); box.setObjectName("controls"); box.setStyleSheet(
            "QFrame#controls { background: #0f1a33; border: 1px solid #1f2b49; border-radius: 12px; padding: 10px; }"
        )
        h = QHBoxLayout(box); h.setSpacing(20)
        min_allowed, max_allowed = QDate(2000, 1, 1), QDate(2100, 12, 31)
        h.addWidget(QLabel("Date Range:"))
        self.date_from = QDateEdit(); self.date_from.setCalendarPopup(True); self.date_from.setDisplayFormat("dd/MM/yyyy")
        self.date_from.setDate(QDate.currentDate().addDays(-7)); self.date_from.setMinimumDate(min_allowed); self.date_from.setMaximumDate(max_allowed)
        self.date_to = QDateEdit(); self.date_to.setCalendarPopup(True); self.date_to.setDisplayFormat("dd/MM/yyyy")
        self.date_to.setDate(QDate.currentDate()); self.date_to.setMinimumDate(min_allowed); self.date_to.setMaximumDate(max_allowed)
        self.range_btn = QPushButton("📅 Select Range"); self.range_btn.clicked.connect(self._open_range_dialog)
        for w in (self.date_from, QLabel("–"), self.date_to, self.range_btn): h.addWidget(w)
        h.addStretch(); self.range_info = QLabel("Last 7 Days"); self.range_info.setStyleSheet("color: #94a3b8; font-size: 12px;"); h.addWidget(self.range_info)
        self.date_from.dateChanged.connect(self._range_changed); self.date_to.dateChanged.connect(self._range_changed)
        self._update_range_info(); return box

    def _kpis(self) -> QWidget:
        frame = QFrame(); h = QHBoxLayout(frame); h.setSpacing(16); h.setContentsMargins(0, 0, 0, 0)
        self.kpi_healthy = self._kpi_card("Overall Healthy %", "0%", "#22c55e")
        self.kpi_images  = self._kpi_card("Images Analyzed", "0",  "#6366f1")
        self.kpi_devices = self._kpi_card("Active Devices", "0", "#f59e0b")
        for k in (self.kpi_healthy, self.kpi_images, self.kpi_devices): h.addWidget(k)
        return frame

    def _cards(self) -> QWidget:
        frame = QFrame(); h = QHBoxLayout(frame); h.setSpacing(16); h.setContentsMargins(0, 0, 0, 0)
        self.devices_card = self._devices_card(); self.diseases_card = self._diseases_card()
        h.addWidget(self.devices_card, 2); h.addWidget(self.diseases_card, 1); return frame

    # Small UI helpers
    def _kpi_card(self, title: str, value: str, color: str) -> QWidget:
        card = QFrame(); card.setProperty("class", "card"); v = QVBoxLayout(card); v.setSpacing(8)
        t = QLabel(title); t.setStyleSheet("font-size: 13px; color: #94a3b8;")
        val = QLabel(value); val.setObjectName("value"); val.setStyleSheet(f"font-size: 28px; font-weight: 700; color: {color};")
        v.addWidget(t); v.addWidget(val); return card

    def _devices_card(self) -> QWidget:
        card = QFrame(); card.setProperty("class", "card"); v = QVBoxLayout(card); v.setSpacing(12)
        title = QLabel("Disease Severity by Device (Top 5)")
        title.setStyleSheet("font-size: 16px; font-weight: 700; letter-spacing: .2px;")
        self.devices_container = QWidget(); self.devices_layout = QVBoxLayout(self.devices_container)
        self.devices_layout.setSpacing(10); self.devices_layout.setContentsMargins(0,0,0,0)
        note = QLabel("Bar color by severity: Green/Orange/Red • Length represents percentage")
        note.setStyleSheet("font-size: 12px; color: #94a3b8; margin-top: 8px;")
        v.addWidget(title); v.addWidget(self.devices_container); v.addStretch(); v.addWidget(note); return card

    def _diseases_card(self) -> QWidget:
        card = QFrame(); card.setProperty("class", "card"); v = QVBoxLayout(card); v.setSpacing(12)
        title = QLabel("Top 3 Most Common Diseases")
        title.setStyleSheet("font-size: 16px; font-weight: 700; letter-spacing: .2px;")
        self.diseases_container = QWidget(); self.diseases_layout = QVBoxLayout(self.diseases_container)
        self.diseases_layout.setSpacing(10); self.diseases_layout.setContentsMargins(0,0,0,0)
        note = QLabel("Click on a disease to view detailed Grafana analytics below")
        note.setStyleSheet("font-size: 12px; color: #94a3b8; margin-top: 8px;")
        v.addWidget(title); v.addWidget(self.diseases_container); v.addStretch(); v.addWidget(note); return card

    def _device_details_card(self) -> QWidget:
        """Card that shows disease breakdown for selected device"""
        card = QFrame(); card.setProperty("class", "card"); v = QVBoxLayout(card); v.setSpacing(12)
        
        # Header with close button
        header = QHBoxLayout()
        self.device_title = QLabel("Device Details")
        self.device_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(self.device_title)
        header.addStretch()
        
        close_btn = QPushButton("✕ Close")
        close_btn.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        close_btn.clicked.connect(lambda: self.device_card.setVisible(False))
        header.addWidget(close_btn)
        
        v.addLayout(header)
        
        self.device_box = QWidget(); self.device_layout = QVBoxLayout(self.device_box)
        self.device_layout.setSpacing(10); self.device_layout.setContentsMargins(0,0,0,0)
        note = QLabel("% represents sick images with this disease out of ALL images from this device")
        note.setStyleSheet("font-size: 12px; color: #94a3b8; margin-top: 8px;")
        v.addWidget(self.device_box); v.addStretch(); v.addWidget(note)
        return card

    def _grafana_details_card(self) -> QWidget:
        """Card that shows embedded Grafana dashboard for selected disease"""
        card = QFrame(); card.setProperty("class", "card"); v = QVBoxLayout(card); v.setSpacing(12)
        v.setContentsMargins(16, 16, 16, 16)
        
        # Header with title and close button
        header = QHBoxLayout()
        self.grafana_title = QLabel("Disease Analysis")
        self.grafana_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        header.addWidget(self.grafana_title)
        header.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        refresh_btn.clicked.connect(self._refresh_grafana)
        header.addWidget(refresh_btn)
        
        close_btn = QPushButton("✕ Close")
        close_btn.setStyleSheet("padding: 4px 8px; font-size: 11px;")
        close_btn.clicked.connect(lambda: self.grafana_card.setVisible(False))
        header.addWidget(close_btn)
        
        v.addLayout(header)
        
        # Grafana WebView (embedded)
        self.grafana_web = QWebEngineView()
        self.grafana_web.setMinimumHeight(700)  # Good size for viewing
        v.addWidget(self.grafana_web)
        
        # Status label
        self.grafana_status = QLabel("📊 Loading dashboard...")
        self.grafana_status.setStyleSheet("padding: 5px; color: #94a3b8; font-size: 11px;")
        v.addWidget(self.grafana_status)
        
        self.grafana_web.loadFinished.connect(self._on_grafana_loaded)
        
        return card

    def _refresh_grafana(self):
        """Refresh the embedded Grafana dashboard"""
        self.grafana_status.setText("📊 Refreshing dashboard...")
        self.grafana_web.reload()

    def _on_grafana_loaded(self, success: bool):
        """Called when Grafana page finishes loading"""
        if success:
            self.grafana_status.setText("✅ Dashboard loaded | Auto-refresh every 10 seconds")
        else:
            self.grafana_status.setText("❌ Error loading dashboard - Ensure Grafana is running")

    # ───────── Data fetch ─────────

    def _load_types(self) -> None:
        """Fetch leaf_disease_types -> self._types {id:str -> name:str}."""
        try:
            url = f"{self.api.base}/api/tables/leaf_disease_types"
            resp = self.api.http.get(url, timeout=10)
            mapping = {
                str(r.get("id")): str(r.get("name"))
                for r in _json_rows(resp.json())
                if isinstance(r, dict) and r.get("id") is not None and r.get("name")
            }
            if mapping:
                self._types = mapping
            print(f"[LeafDiseaseView] Loaded {len(self._types)} disease types.")
        except Exception as e:
            print(f"[LeafDiseaseView] Failed loading disease types: {e}")

    def _load_reports(self) -> None:
        """Fetch reports -> self._raw and update."""
        try:
            url = f"{self.api.base}/api/tables/leaf_reports"
            print(f"[LeafDiseaseView] Requesting: {url}")
            resp = self.api.http.get(url)
            rows = _json_rows(resp.json()) if resp.status_code == 200 else []
            if rows and isinstance(rows[0], str):  # stringified JSON rows support
                import json
                rows = [json.loads(x) if isinstance(x, str) else x for x in rows]
            self._raw = [r for r in rows if isinstance(r, dict)]
            self._update_all(self._filter_by_dates(self._raw))
        except Exception as e:
            print(f"[LeafDiseaseView] Error: {e}")
            self._update_all([])

    # ───────── Filters & triggers ─────────

    def _range_changed(self, *_):
        self._update_range_info()
        self._filters_timer.start()

    def _open_range_dialog(self):
        dlg = DateRangeDialog(self, start=self.date_from.date(), end=self.date_to.date())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            f, t = dlg.selectedRange()
            if f and t:
                self.date_from.setDate(f)
                self.date_to.setDate(t)
            else:
                self.date_from.setDate(QDate.currentDate().addDays(-7))
                self.date_to.setDate(QDate.currentDate())
            self._range_changed()

    def _update_range_info(self):
        txt = f"{self.date_from.date().toString('dd/MM')} → {self.date_to.date().toString('dd/MM')}"
        self.range_info.setText(txt)
        self.range_btn.setText(f"📅 {txt}")

    def _apply_filters_and_update(self):
        self._update_all(self._filter_by_dates(self._raw))

    def _filter_by_dates(self, data: list[dict]) -> list[dict]:
        """Inclusive date-only filter using QDate edits."""
        d_from, d_to = self.date_from.date().toPyDate(), self.date_to.date().toPyDate()
        out = []
        for r in data:
            ts = r.get("ts")
            if ts:
                d = _ts_to_date(ts)
                if d and not (d_from <= d <= d_to):
                    continue
            out.append(r)
        print(f"[KPI-DBG] filter_by_dates: kept={len(out)} of {len(data)}")
        return out

    # ───────── Update UI ─────────

    def _update_all(self, filtered: list[dict]) -> None:
        self._update_kpis(filtered)
        self._update_devices(filtered)
        self._update_diseases(filtered)
        if self.device_card.isVisible() and hasattr(self, "_sel_dev"):
            self._render_device(self._sel_dev, filtered)

    def _update_kpis(self, data: list[dict]) -> None:
        total = len(data)
        if total == 0:
            self.kpi_healthy.findChild(QLabel, "value").setText("0%")
            self.kpi_images.findChild(QLabel, "value").setText("0")
            self.kpi_devices.findChild(QLabel, "value").setText("0")
            return
        sick = sum(1 for r in data if _is_sick(r.get("sick")))
        healthy_pct = (total - sick) / total * 100
        devices = len({str(r.get("device_id")) for r in data if r.get("device_id")})
        self.kpi_healthy.findChild(QLabel, "value").setText(f"{healthy_pct:.1f}%")
        self.kpi_images.findChild(QLabel, "value").setText(f"{total:,}")
        self.kpi_devices.findChild(QLabel, "value").setText(str(devices))

    # ── Devices: top-5 ──

    def _update_devices(self, data: list[dict]) -> None:
        _clear_layout(self.devices_layout)
        if not data:
            return
        stats = defaultdict(lambda: {"total": 0, "sick": 0})
        for r in data:
            dev = r.get("device_id")
            if not dev:
                continue
            s = stats[str(dev)]
            s["total"] += 1
            if _is_sick(r.get("sick")):
                s["sick"] += 1
        pairs = [(dev, (s["sick"] / s["total"] * 100.0 if s["total"] else 0.0)) for dev, s in stats.items()]
        for dev, pct in sorted(pairs, key=lambda x: x[1], reverse=True)[:5]:
            row = self._build_bar_row(title=str(dev), pct=pct, right_text=f"{pct:.1f}%")
            row.clicked.connect(self._on_device_clicked)
            self.devices_layout.addWidget(row)

    def _on_device_clicked(self, device_id: str) -> None:
        """When device is clicked, hide Grafana and show device details"""
        self._sel_dev = device_id
        self.grafana_card.setVisible(False)  # Hide Grafana if open
        self._render_device(device_id, self._filter_by_dates(self._raw))

    def _render_device(self, device_id: str, data: list[dict]) -> None:
        """
        Shows diseases for selected device.
        IMPORTANT: % = (sick images with this disease) / (ALL images from device) * 100
        """
        _clear_layout(self.device_layout)
        
        # Get all images from this device
        device_data = [r for r in data if str(r.get("device_id", "")) == str(device_id)]
        total_device_images = len(device_data)
        
        if total_device_images == 0:
            self.device_card.setVisible(False)
            return
        
        # Count sick images per disease type
        disease_sick_counts = defaultdict(int)
        for r in device_data:
            if _is_sick(r.get("sick")):
                did = r.get("leaf_disease_type_id")
                if did is not None:
                    disease_sick_counts[str(did)] += 1
        
        self.device_title.setText(f"Device: {device_id} – Disease Breakdown")
        
        # Calculate % of total device images
        rows = []
        for did, sick_count in disease_sick_counts.items():
            pct = (sick_count / total_device_images * 100.0) if total_device_images else 0.0
            rows.append((self._disease_name(did), pct, sick_count, total_device_images))
        
        # Sort by percentage and display
        for name, pct, sick_cnt, total_imgs in sorted(rows, key=lambda x: x[1], reverse=True):
            txt = f"{pct:.1f}%  ({sick_cnt}/{total_imgs} images)"
            self.device_layout.addWidget(self._build_bar_row(title=name, pct=pct, right_text=txt))
        
        self.device_card.setVisible(True)

    # ── Diseases: top-3 ──

    def _update_diseases(self, data: list[dict]) -> None:
        _clear_layout(self.diseases_layout)
        if not data:
            return
        counter: Counter[str] = Counter()
        for r in data:
            if _is_sick(r.get("sick")):
                did = r.get("leaf_disease_type_id")
                if did is not None:
                    counter[str(did)] += 1
        total_sick = sum(counter.values()) or 1
        palette = ["#f97316", "#eab308", "#ef4444"]
        for i, (did, cnt) in enumerate(counter.most_common(3)):
            name = self._disease_name(did)
            pct = cnt / total_sick * 100.0
            color = palette[i] if i < len(palette) else "#6366f1"
            self.diseases_layout.addWidget(
                self._build_tag(name=name, disease_id=str(did), color=color, pct=pct, count=cnt)
            )

    # ── Disease details: Shows embedded Grafana below ──

    def _on_disease_clicked(self, disease_id: str) -> None:
        """When disease is clicked, hide device details and show Grafana below"""
        disease_name = self._disease_name(disease_id)
        print(f"[LeafDiseaseView] Showing Grafana for disease: {disease_name} (ID: {disease_id})")
        
        # Hide device card if open
        self.device_card.setVisible(False)
        
        # Update Grafana title and load dashboard
        self.grafana_title.setText(f"📊 Disease Analysis: {disease_name}")
        
        # Build Grafana URL with disease_id variable
        grafana_url = (
            f"http://host.docker.internal:3000/d/leaf-disease-detail/"
            f"leaf-disease-analysis"
            f"?orgId=1&refresh=10s&kiosk=tv"
            f"&var-disease_id={disease_id}"
        )
        
        print(f"[LeafDiseaseView] Loading Grafana: {grafana_url}")
        self.grafana_status.setText("📊 Loading dashboard...")
        self.grafana_web.setUrl(QUrl(grafana_url))
        
        # Show Grafana card
        self.grafana_card.setVisible(True)

    # ───────── Reusable tiny builders ─────────
    def _build_bar_row(self, title: str, pct: float, right_text: str) -> ClickableRow:
        """
        Generic row: title | QProgressBar (color by pct) | right text.
        Bar length represents the percentage value.
        """
        row = ClickableRow(title)
        h = QHBoxLayout(row)
        h.setSpacing(10)
        h.setContentsMargins(0, 0, 0, 0)

        # left title
        name = QLabel(title)
        name.setStyleSheet("font-weight: 600; min-width: 180px;")
        h.addWidget(name)

        # middle: progress bar (VALUE = pct, so bar length represents percentage)
        pb = QProgressBar()
        pb.setRange(0, 100)
        pb.setValue(int(max(0, min(100, pct))))
        pb.setTextVisible(False)

        # color chunk dynamically by severity
        chunk_color = _color_for_pct(pct)  # green/orange/red
        pb.setStyleSheet(
            "QProgressBar { background: #0b1220; border: 1px solid #1f2937; "
            "border-radius: 999px; min-height: 14px; max-height: 14px; } "
            f"QProgressBar::chunk {{ background: {chunk_color}; border-radius: 999px; }}"
        )
        h.addWidget(pb, 1)

        # right label
        r = QLabel(right_text)
        r.setStyleSheet("color: #94a3b8; min-width: 110px;")
        r.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(r)

        return row

    def _build_tag(self, name: str, disease_id: str, color: str, pct: float, count: int) -> ClickableTag:
        row = ClickableTag(disease_id)
        h = QHBoxLayout(row)
        h.setSpacing(8)
        h.setContentsMargins(0, 0, 0, 0)
        
        tag = QFrame()
        tag.setStyleSheet("background: #0b1220; border: 1px solid #1f2937; border-radius: 999px; padding: 6px 10px;")
        tag_h = QHBoxLayout(tag)
        tag_h.setSpacing(8)
        tag_h.setContentsMargins(6, 4, 6, 4)
        
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {color}; font-size: 16px;")
        disp = name if len(name) <= 25 else name[:25] + "…"
        tag_h.addWidget(dot)
        tag_h.addWidget(QLabel(disp))
        
        h.addWidget(tag)
        h.addStretch()
        
        pct_lbl = QLabel(f"{pct:.0f}% ({count} reports)")
        pct_lbl.setStyleSheet("color: #94a3b8; font-size: 13px;")
        h.addWidget(pct_lbl)
        
        row.clicked.connect(self._on_disease_clicked)
        return row

    # ───────── Naming ─────────

    def _disease_name(self, disease_id: str | int | None) -> str:
        if disease_id is None:
            return "Unknown Disease"
        return self._types.get(str(disease_id), f"Disease #{disease_id}")