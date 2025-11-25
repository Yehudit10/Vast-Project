from __future__ import annotations
from datetime import date

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QDateEdit, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect, QSplitter, QLineEdit, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QDate
from PyQt6.QtGui import QColor
from PyQt6 import QtCore

from orthophoto_canvas.ui.viewer_factory import create_orthophoto_viewer
from src.vast.views.security.analytics.map_layers.region_layer import RegionLayer
from src.vast.views.security.analytics.map_layers.device_layer import DeviceLayer
from src.vast.views.security.analytics.analytics_provider import (
    load_all_devices, load_all_regions,
    get_region_analytics, get_device_analytics
)
from src.vast.views.security.analytics.popup_panel import AnalyticsPanel
from src.vast.views.security.analytics import analytics_provider as ap


class AgGuardMessageBox(QFrame):
    def __init__(self, parent=None, title="Message", text=""):
        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        # no translucent background → no black corners
        self.setAutoFillBackground(True)
        pal = self.palette()
        pal.setColor(self.backgroundRole(), QColor("#fefefe"))
        self.setPalette(pal)

        # Light drop shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 3)
        shadow.setColor(QColor(200, 200, 200, 90))
        self.setGraphicsEffect(shadow)

        self.setStyleSheet("""
            QFrame {
                background-color: #fefefe;
                border-radius: 16px;
                border: 1px solid #f3f4f6;
            }
            QLabel#title {
                font-size: 18px;
                font-weight: 700;
                color: #1f2937;
            }
            QLabel#text {
                font-size: 14px;
                color: #4b5563;
            }
            QPushButton#ok_btn {
                background-color: #10b981;
                color: white;
                border-radius: 10px;
                padding: 6px 18px;
                font-weight: 600;
                min-width: 80px;
            }
            QPushButton#ok_btn:hover {
                background-color: #059669;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("title")

        text_lbl = QLabel(text)
        text_lbl.setObjectName("text")
        text_lbl.setWordWrap(True)

        btn = QPushButton("OK")
        btn.setObjectName("ok_btn")
        btn.clicked.connect(self.close)

        layout.addWidget(title_lbl)
        layout.addWidget(text_lbl)
        layout.addStretch()
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.adjustSize()
        self.setMinimumWidth(360)

    def show_centered(self):
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
            self.move(x, y)
        self.show()


class GeoAnalyticsView(QWidget):
    """Geo-Analytics Dashboard with fixed analytics panel and multi-selection."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.current_mode = "region"
        self.start_date: date | None = None
        self.end_date: date | None = None
        self.selected_regions = set()
        self.selected_devices = set()

        # ─────────────────────────────
        # GLOBAL STYLE
        # ─────────────────────────────
        self.setStyleSheet("""
            QWidget {
                background-color: #f9fafb;
                font-family: 'Segoe UI', 'DejaVu Sans', Arial, sans-serif;
                color: #111827;
                font-size: 14px;
            }
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
            QPushButton#apply_btn {
                background-color: #10b981;
                color: white;
                border-radius: 6px;
                font-weight: 600;
                padding: 6px 12px;
            }
            QPushButton#apply_btn:hover { background-color: #059669; }
        """)

        # ─────────────────────────────
        # ROOT LAYOUT
        # ─────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Header
        header = QLabel("🗺️ Geo-Analytics Dashboard")
        header.setStyleSheet("font-size:22px;font-weight:700;color:#0f172a;")
        root.addWidget(header)

        # ─────────────────────────────
        # FILTER BAR
        # ─────────────────────────────
        filter_frame = QFrame()
        filter_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #d1d5db;
                border-radius: 12px;
                padding: 10px 14px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 40))
        filter_frame.setGraphicsEffect(shadow)

        filter_bar = QHBoxLayout(filter_frame)
        filter_bar.setSpacing(14)
        filter_bar.setContentsMargins(10, 6, 10, 6)

        lbl_mode = QLabel("Mode:")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Region", "Device"])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        lbl_date = QLabel("Date range:")
        self.start_picker = QDateEdit(QDate.currentDate().addMonths(-1))
        self.start_picker.setCalendarPopup(True)
        arrow_lbl = QLabel("→")
        self.end_picker = QDateEdit(QDate.currentDate())
        self.end_picker.setCalendarPopup(True)

        apply_btn = QPushButton("Apply Filters")
        apply_btn.setObjectName("apply_btn")
        apply_btn.clicked.connect(self._apply_filters)

        filter_bar.addWidget(lbl_mode)
        filter_bar.addWidget(self.mode_combo)
        filter_bar.addSpacing(12)
        filter_bar.addWidget(lbl_date)
        filter_bar.addWidget(self.start_picker)
        filter_bar.addWidget(arrow_lbl)
        filter_bar.addWidget(self.end_picker)
        filter_bar.addSpacing(12)
        filter_bar.addWidget(apply_btn)
        filter_bar.addStretch()
        root.addWidget(filter_frame)

        # ─────────────────────────────
        # AI QUERY BAR
        # ─────────────────────────────
        query_frame = QFrame()
        query_frame.setStyleSheet("""
            QFrame {
                background-color: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 18px;
                padding: 10px 12px;
            }
            QLineEdit {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 #ffffff, stop:1 #f9fafb
                );
                border: 1px solid #d1d5db;
                border-radius: 18px;
                padding: 8px 16px;
                font-size: 14px;
                color: #111827;
                selection-background-color: #bae6fd;
            }
            QLineEdit:focus {
                border-color: #10b981;
                background-color: #ffffff;
                box-shadow: 0 0 0 3px rgba(16,185,129,0.2);
            }
            QPushButton#send_btn {
                background-color: #10b981;
                color: white;
                font-weight: 600;
                border-radius: 18px;
                padding: 0 18px;
                border: none;
                min-width: 80px;
                height: 38px;
            }
            QPushButton#send_btn:hover {
                background-color: #059669;
            }
        """)

        query_layout = QHBoxLayout(query_frame)
        query_layout.setSpacing(8)
        query_layout.setContentsMargins(10, 6, 10, 6)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Ask anything — e.g. 'Show regions with most intrusions this month'")
        self.query_input.setClearButtonEnabled(True)
        self.query_input.setMinimumWidth(420)
        self.query_input.setFixedHeight(38)

        self.query_send = QPushButton("Send")
        self.query_send.setObjectName("send_btn")
        self.query_send.clicked.connect(self._on_query_sent)

        query_layout.addWidget(self.query_input, stretch=1)
        query_layout.addWidget(self.query_send)

        query_shadow = QGraphicsDropShadowEffect()
        query_shadow.setBlurRadius(22)
        query_shadow.setOffset(0, 3)
        query_shadow.setColor(QColor(0, 0, 0, 50))
        query_frame.setGraphicsEffect(query_shadow)

        # ─────────────────────────────
        # MAIN SPLITTER (map + analytics)
        # ─────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #e5e7eb;
            }
            QSplitter::handle:hover {
                background-color: #10b981;
            }
        """)

        # ─────────────────────────────
        # LEFT SIDE — map card + query box
        # ─────────────────────────────
        map_container = QWidget()
        map_container_layout = QVBoxLayout(map_container)
        map_container_layout.setContentsMargins(0, 0, 0, 0)
        map_container_layout.setSpacing(0)

        # Outer shell (white card with strong round corners + shadow)
        map_shell = QFrame()
        map_shell.setObjectName("mapShell")
        map_shell.setStyleSheet("""
            QFrame#mapShell {
                background-color: #ffffff;
                border-radius: 24px;
                border: 1px solid #e5e7eb;
            }
        """)
        map_shell_shadow = QGraphicsDropShadowEffect()
        map_shell_shadow.setBlurRadius(26)
        map_shell_shadow.setOffset(0, 8)
        map_shell_shadow.setColor(QColor(15, 23, 42, 55))
        map_shell.setGraphicsEffect(map_shell_shadow)

        shell_layout = QVBoxLayout(map_shell)
        shell_layout.setContentsMargins(14, 14, 14, 14)
        shell_layout.setSpacing(10)

        # Inner rounded frame that actually clips the map
        map_frame = QFrame()
        map_frame.setObjectName("mapFrame")
        map_frame.setStyleSheet("""
            QFrame#mapFrame {
                background-color: #020617;    /* dark slate */
                border-radius: 18px;
                border: none;
            }
        """)
        map_frame.setContentsMargins(0, 0, 0, 0)
        map_frame_layout = QVBoxLayout(map_frame)
        map_frame_layout.setContentsMargins(0, 0, 0, 0)
        map_frame_layout.setSpacing(0)

        tiles_root = "./src/vast/orthophoto_canvas/data/tiles"
        self.viewer = create_orthophoto_viewer(tiles_root, forced_scheme=None, parent=self)

        # Make the view itself frameless and rounded
        self.viewer.setFrameShape(QFrame.Shape.NoFrame)
        self.viewer.setStyleSheet("""
            QGraphicsView {
                background-color: transparent;
                border: none;
            }
            QGraphicsView::viewport {
                border-radius: 18px;   /* real rounded viewport */
                background-color: #020617;
            }
        """)
        self.viewer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Optional static background instead of tiles
        self.viewer.set_custom_background_image(
            "./src/vast/orthophoto_canvas/ui/fields.png",
            hide_tiles=True
        )
        self.viewer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        map_frame_layout.addWidget(self.viewer, stretch=1)

        # Query bar sits under the map, inside the same shell
        query_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        shell_layout.addWidget(map_frame, stretch=1)
        shell_layout.addWidget(query_frame, stretch=0)

        map_container_layout.addWidget(map_shell)
        splitter.addWidget(map_container)


        # ─────────────────────────────
        # RIGHT SIDE — analytics panel
        # ─────────────────────────────
        self.analytics_panel = AnalyticsPanel("All Regions", {}, parent=self)
        self.analytics_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self.analytics_panel)

        root.addWidget(splitter, stretch=1)

        # ─────────────────────────────
        # MAP LAYERS
        # ─────────────────────────────
        self.region_layer = RegionLayer(self.viewer, on_select=self._on_region_selected)
        self.device_layer = DeviceLayer(self.viewer, on_select=self._on_device_selected)

        # Initial load
        self._load_regions()
        self._update_analytics_panel()
        self._initial_fit_done = False
        QtCore.QTimer.singleShot(0, self._fit_map_to_container)

    # Ensure map always fills its container nicely
    def resizeEvent(self, event):
        super().resizeEvent(event)
        QtCore.QTimer.singleShot(0, self._fit_map_to_container)

    def _fit_map_to_container(self):
        """
        Make the map fill the entire map container (no gray bars).
        Run after layouts/child resizes using QTimer.singleShot.
        """
        if not hasattr(self, "viewer") or self.viewer is None:
            return

        scene_rect = self.viewer.scene.sceneRect()
        if scene_rect.isNull():
            return

        self.viewer.fitInView(scene_rect, Qt.AspectRatioMode.KeepAspectRatioByExpanding)
        self.viewer.centerOn(scene_rect.center())

    # ─────────────────────────────
    # FREE TEXT QUERY HANDLER
    # ─────────────────────────────
    def _on_query_sent(self):
        prompt = self.query_input.text().strip()
        if not prompt:
            QMessageBox.information(self, "Empty query", "Please type a query first.")
            return

        # Change button state
        self.query_send.setEnabled(False)
        self.query_send.setText("...")
        QApplication.processEvents()

        try:
            result = ap.select_entities_from_prompt(prompt)
        except Exception as e:
            dlg = AgGuardMessageBox(
                self,
                title="Invalid Query",
                text="We couldn't understand your request.\nPlease try rephrasing your query or using clearer terms."
            )
            dlg.show_centered()

            # restore state and abort
            self.query_send.setEnabled(True)
            self.query_send.setText("Send")
            return

        # Restore state
        self.query_send.setEnabled(True)
        self.query_send.setText("Send")

        if not result["ids"]:
            QMessageBox.information(self, "No results", "No matching regions or devices found.")
            return

        if result["target"] == "region":
            self.current_mode = "region"
            self.mode_combo.setCurrentText("Region")
            self._update_layer_visibility()
            self.device_layer.clear()
            self.selected_regions = set(map(int, result["ids"]))
            self.region_layer.clear()
            self._load_regions(self.start_picker.date().toPyDate(),
                               self.end_picker.date().toPyDate())

        elif result["target"] == "device":
            self.current_mode = "device"
            self.mode_combo.setCurrentText("Device")
            self._update_layer_visibility()
            self.region_layer.clear()
            self.selected_devices = set(map(str, result["ids"]))
            self.device_layer.clear()
            self._load_devices(
                self.start_picker.date().toPyDate(),
                self.end_picker.date().toPyDate(),
                selected_ids=self.selected_devices
            )

        self._update_analytics_panel()

    # ─────────────────────────────
    # MODE / FILTERS
    # ─────────────────────────────
    def _on_mode_changed(self, text: str):
        self.current_mode = text.lower()
        if self.current_mode == "region":
            self.device_layer.clear()
        else:
            self.region_layer.clear()
        self._update_layer_visibility()
        self._apply_filters()

    def _apply_filters(self):
        self.start_date = self.start_picker.date().toPyDate()
        self.end_date = self.end_picker.date().toPyDate()
        self.region_layer.clear()
        self.device_layer.clear()
        self.selected_regions.clear()
        self.selected_devices.clear()
        self._update_layer_visibility()
        if self.current_mode == "region":
            self._load_regions(self.start_date, self.end_date)
        else:
            self._load_devices(self.start_date, self.end_date)
        self._update_analytics_panel()

    # ─────────────────────────────
    # LOADERS
    # ─────────────────────────────
    def _load_regions(self, start_date=None, end_date=None):
        regions = load_all_regions()
        self.region_names = {r["id"]: r["name"] for r in regions}
        for region in regions:
            self.region_layer.add_region(region, start_date, end_date, selected_ids=self.selected_regions)

    def _load_devices(self, start_date=None, end_date=None, selected_ids=None):
        devices = load_all_devices()
        for device in devices:
            device_id = device["device_id"]
            selected = selected_ids and device_id in selected_ids
            self.device_layer.add_device(device, start_date, end_date, selected=selected)

    # ─────────────────────────────
    # SELECTION HANDLERS
    # ─────────────────────────────
    def _on_region_selected(self, region_id: int, selected: bool):
        if selected:
            self.selected_regions.add(region_id)
        else:
            self.selected_regions.discard(region_id)
        self._update_analytics_panel()

    def _on_device_selected(self, device_id: str, selected: bool):
        if selected:
            self.selected_devices.add(device_id)
        else:
            self.selected_devices.discard(device_id)
        self._update_analytics_panel()

    # ─────────────────────────────
    # ANALYTICS UPDATE
    # ─────────────────────────────
    def _update_analytics_panel(self):
        if self.current_mode == "region":
            region_list = list(self.selected_regions)
            data = get_region_analytics(region_list or None, self.start_date, self.end_date)
            title = "All Regions" if not region_list else ", ".join(
                self.region_names.get(rid, str(rid)) for rid in region_list)
            self.analytics_panel.update_data(title, data)
        else:
            device_list = list(self.selected_devices)
            data = get_device_analytics(device_list or None, self.start_date, self.end_date)
            title = "All Devices" if not device_list else ", ".join(device_list)
            self.analytics_panel.update_data(title, data)

    def _update_layer_visibility(self):
        if self.current_mode == "region":
            self.region_layer.setVisible(True)
            self.device_layer.setVisible(False)
        else:
            self.region_layer.setVisible(False)
            self.device_layer.setVisible(True)
