from PyQt6.QtWidgets import (
    QGraphicsTextItem, QGraphicsItem, QLabel, QVBoxLayout, QWidget
)

from PyQt6.QtCore import (
    Qt, QPoint, QPointF
)
from src.vast.orthophoto_canvas.ui.sensors_layer import _latlon_to_base_xy_if_inside, TILE_SIZE
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import QGraphicsDropShadowEffect


# ─────────────────────────────────────────────
# Frameless Popup Widget
# ─────────────────────────────────────────────
class AlertPopupWidget(QWidget):
    """Modern frameless popup with real rounded corners and drop shadow."""

    def __init__(self, html: str, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel()
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setText(html)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setStyleSheet("""
            QLabel {
                background-color: #ffffff;
                border: 2px solid #444;
                border-radius: 16px;
                padding: 14px 16px;
                font-family: 'Segoe UI', 'Roboto';
                font-size: 13px;
                color: #111;
            }
        """)

        layout.addWidget(label)

        # Drop shadow around the widget
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(shadow)

        self.adjustSize()

    def show_near(self, global_pos: QPoint):
        """Position popup slightly above and to the right of the marker."""
        self.adjustSize()
        self.move(global_pos + QPoint(12, -self.height() - 12))
        self.show()


# ─────────────────────────────────────────────
# Marker Item
# ─────────────────────────────────────────────
class _AlertMarker(QGraphicsTextItem):
    """A single alert marker (emoji icon) that shows a modern popup on hover."""

    def __init__(self, alert_id, alert_data, *args, **kwargs):
        icon = {1: "⚠️", 2: "🚨", 3: "🚨"}.get(int(alert_data.get("severity", 1)), "⚠️")
        super().__init__(icon, *args, **kwargs)

        self.alert_id = alert_id
        self.alert_data = alert_data
        self._popup = None

        self.setZValue(1_000_000)
        self.setFont(QFont("Noto Color Emoji", 8))
        self.setDefaultTextColor(QColor("#222"))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        alert = self.alert_data
        severity = int(alert.get("severity", 1))

        severity_color = {
            1: "#ffcc00",  # yellow warning
            2: "#ff6666",  # red alert
            2: "#ff6666",
        }.get(severity, "#999")

        tooltip_html = f"""
        <div style="
            font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif;
            font-size: 13px;
            color: #222;
            background: linear-gradient(180deg, #ffffff 0%, #f7f8fa 100%);
            border-radius: 14px;
            border: 1px solid rgba(0,0,0,0.15);
            padding: 14px 18px;
            min-width: 260px;
            box-shadow: 0 4px 16px rgba(0,0,0,0.15);
        ">

        <!-- Header -->
        <div style="
            font-size: 15px;
            font-weight: 600;
            color: {severity_color};
            margin-bottom: 8px;
            text-transform: capitalize;
        ">
            {alert.get('alert_type','Alert').replace('_',' ')}
        </div>

        <!-- Meta Info -->
        <table style="font-size: 13px; color: #333; line-height: 1.6; border-collapse: collapse;">
            <tr><td style='width:85px; font-weight:500;'>Device:</td><td>{alert.get('device_id','N/A')}</td></tr>
            <tr><td style='font-weight:500;'>Area:</td><td>{alert.get('area','')}</td></tr>
            <tr><td style='font-weight:500;'>Severity:</td><td>{severity}</td></tr>
            <tr><td style='font-weight:500;'>Confidence:</td><td>{alert.get('confidence','')}</td></tr>
        </table>

        <!-- Description -->
        <div style="
            margin-top:12px;
            padding:10px 12px;
            border-radius:10px;
            background:#f9fafb;
            border:1px solid rgba(0,0,0,0.08);
            color:#444;
            font-style:italic;
            line-height:1.5;
        ">
            {alert.get('summary','No additional details available.')}
        </div>

        </div>
        """


        view = self.scene().views()[0] if self.scene().views() else None
        if view:
            global_pos = view.mapToGlobal(view.mapFromScene(self.scenePos()))
            self._popup = AlertPopupWidget(tooltip_html)
            self._popup.show_near(global_pos)

        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self._popup:
            self._popup.close()
            self._popup = None
        super().hoverLeaveEvent(event)


# ─────────────────────────────────────────────
# Alert Layer
# ─────────────────────────────────────────────
class AlertLayer:
    """Draws alert markers (icons) directly onto the OrthophotoViewer scene."""

    def __init__(self, viewer):
        self.viewer = viewer
        self.scene = viewer.scene
        self.alerts = {}

        self._x_min_base = viewer.ts.z_ranges[viewer.min_zoom_fs][0]
        self._y_min_base = viewer.ts.z_ranges[viewer.min_zoom_fs][2]

    def add_or_update_alert(self, alert: dict):
        alert_id = alert.get("alert_id")
        lat, lon = alert.get("lat"), alert.get("lon")
        if lat is None or lon is None:
            print(f"[AlertLayer] ⚠️ Missing lat/lon for {alert_id}")
            return

        pos = _latlon_to_base_xy_if_inside(self.viewer, float(lat), float(lon), z=self.viewer.max_zoom_fs)
        if not pos:
            print(f"[AlertLayer] ⚠️ Alert {alert_id} outside dataset bounds")
            return

        xb, yb = pos
        scene_x = (xb - self._x_min_base) * TILE_SIZE
        scene_y = (yb - self._y_min_base) * TILE_SIZE
        print(f"[AlertLayer] Alert {alert_id}: scene=({scene_x:.1f}, {scene_y:.1f})")

        if alert_id in self.alerts:
            old_marker, old_label = self.alerts.pop(alert_id)
            self.scene.removeItem(old_marker)
            if old_label:
                self.scene.removeItem(old_label)

        # Create marker
        marker = _AlertMarker(alert_id, alert)
        marker.setPos(scene_x, scene_y)
        self.scene.addItem(marker)

        # Optional label (area name)
        label_text = alert.get("area", "")
        if label_text:
            label_item = QGraphicsTextItem(label_text)
            label_item.setDefaultTextColor(Qt.GlobalColor.black)
            label_item.setFont(QFont("Segoe UI", 8))
            label_item.setPos(scene_x + 8, scene_y - 8)
            label_item.setZValue(9_999_998)
            label_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            self.scene.addItem(label_item)
        else:
            label_item = None

        self.alerts[alert_id] = (marker, label_item)

    def clear_alerts(self):
        print("[AlertLayer] Clearing all alert markers")
        for marker, label in self.alerts.values():
            self.scene.removeItem(marker)
            if label:
                self.scene.removeItem(label)
        self.alerts.clear()
    def remove_alert(self, alert_id: str):
        """Remove a specific alert marker from the scene."""
        if alert_id not in self.alerts:
            print(f"[AlertLayer] ⚠️ Tried to remove unknown alert_id: {alert_id}")
            return

        marker, label = self.alerts.pop(alert_id)
        if marker:
            self.scene.removeItem(marker)
        if label:
            self.scene.removeItem(label)
        print(f"[AlertLayer] ❌ Removed alert marker: {alert_id}")

