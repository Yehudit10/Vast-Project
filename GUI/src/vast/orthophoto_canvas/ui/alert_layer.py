from PyQt6.QtWidgets import (
    QGraphicsTextItem, QLabel, QVBoxLayout, QWidget, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QColor, QFont
from src.vast.orthophoto_canvas.ui.sensors_layer import _latlon_to_xy_at_max_zoom, TILE_SIZE


# ─────────────────────────────────────────────
# Frameless Popup Widget
# ─────────────────────────────────────────────
class AlertPopupWidget(QWidget):
    """Frameless popup with rounded corners, colored border, and drop shadow."""

    def __init__(self, html: str, border_color: str = "#444", parent=None):
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
        label.setStyleSheet(f"""
            QLabel {{
                background-color: #ffffff;
                border: 2px solid {border_color};
                border-radius: 12px;
                padding: 10px 12px;
                font-family: 'Segoe UI', 'Roboto', 'Helvetica Neue', sans-serif;
                font-size: 12px;
                color: #111;
            }}
        """)
        layout.addWidget(label)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)

        self.adjustSize()

    def show_near(self, global_pos: QPoint):
        """Show popup slightly above and to the right of the marker."""
        self.adjustSize()
        self.move(global_pos + QPoint(12, -self.height() - 12))
        self.show()


# ─────────────────────────────────────────────
# Marker Item
# ─────────────────────────────────────────────
class _AlertMarker(QGraphicsTextItem):
    """A single alert marker (emoji icon) that shows a modern popup on hover."""

    def __init__(self, alert_id, alert_data, *args, **kwargs):
        severity = int(alert_data.get("severity", 1))
        icon = {1: "⚠️", 2: "🚨"}.get(severity, "🚨")
        super().__init__(icon, *args, **kwargs)

        self.alert_id = alert_id
        self.alert_data = alert_data
        self._popup = None

        self.setZValue(1_000_000)
        self.setFont(QFont("Noto Color Emoji", 12))
        self.setDefaultTextColor(QColor("#222"))
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)

    def hoverEnterEvent(self, event):
        alert = self.alert_data
        severity = int(alert.get("severity", 1))
        alert_type = alert.get("alert_type", "Alert").replace("_", " ")
        device_id = alert.get("device_id", "unknown")
        summary = alert.get("summary") or "No additional details."
        started_at = alert.get("startsAt", "")

        border_color = {1: "#f1c232", 2: "#f39c12", 3: "#e67e22",
                        4: "#cc0000", 5: "#8b0000"}.get(severity, "#999")

        tooltip_html = f"""
        <div style="background:#ffffff; border-radius:10px; color:#222;
                    font-family:'Segoe UI','Roboto','Helvetica Neue',sans-serif;
                    font-size:12px; min-width:220px;">
            <div style="display:flex; align-items:center;
                        font-size:13px; font-weight:600; margin-bottom:6px;">
                <span style="font-size:15px; margin-right:6px;">{self.toPlainText()}</span>
                <span>{alert_type.capitalize()} detected</span>
            </div>
            <div style="height:1px; background:rgba(0,0,0,0.1); margin:4px 0 6px 0;"></div>
            <div style="display:flex; align-items:flex-start; line-height:1.4; color:#333;">
                <span style="font-size:13px; margin-right:6px;">💬</span>
                <span>{summary}</span>
            </div>
            {f'<div style="margin-top:6px; font-size:11px; color:#777;">🕒 {started_at}</div>' if started_at else ''}
        </div>
        """

        view = self.scene().views()[0] if self.scene().views() else None
        if view:
            global_pos = view.mapToGlobal(view.mapFromScene(self.scenePos()))
            self._popup = AlertPopupWidget(tooltip_html, border_color=border_color)
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
    """Draws alert markers on the orthophoto scene, consistent with RegionLayer projection."""

    def __init__(self, viewer):
        self.viewer = viewer
        self.scene = viewer.scene
        self.alerts = {}

        # Use same base tile coordinates as RegionLayer (max zoom)
        z = viewer.max_zoom_fs
        self._x_min_base = viewer.ts.z_ranges[z][0]
        self._y_min_base = viewer.ts.z_ranges[z][2]

    def add_or_update_alert(self, alert: dict):
        """Add or update a marker for the given alert."""
        if not alert:
            return

        alert_id = alert.get("alert_id") or alert.get("id") or alert.get("alertId")
        if not alert_id:
            print("[AlertLayer] ⚠️ Skipping alert without ID:", alert)
            return

        # Parse coordinates
        lat = alert.get("lat") or alert.get("latitude") or alert.get("location_lat")
        lon = alert.get("lon") or alert.get("longitude") or alert.get("location_lon")
        try:
            lat = float(lat)
            lon = float(lon)
        except Exception:
            print(f"[AlertLayer] ⚠️ Invalid lat/lon for {alert_id}: {lat}, {lon}")
            return

        pos = _latlon_to_xy_at_max_zoom(self.viewer, lat, lon)
        if not pos:
            print(f"[AlertLayer] ⚠️ Alert {alert_id} outside dataset bounds")
            return

        xb, yb = pos
        scene_x = (xb - self._x_min_base) * TILE_SIZE
        scene_y = (yb - self._y_min_base) * TILE_SIZE
        print(f"[AlertLayer] Alert {alert_id}: scene=({scene_x:.1f}, {scene_y:.1f})")

        # Remove old marker if exists
        if alert_id in self.alerts:
            old_marker, _ = self.alerts.pop(alert_id)
            self.scene.removeItem(old_marker)

        severity = int(alert.get("severity", 1))
        normalized = {
            "alert_id": alert_id,
            "alert_type": alert.get("alert_type") or "alert",
            "device_id": alert.get("device_id") or "unknown",
            "area": alert.get("area") or "",
            "severity": severity,
            "confidence": alert.get("confidence") or 0,
            "summary": alert.get("summary") or alert.get("meta") or "",
            "startsAt": alert.get("started_at") or alert.get("startsAt") or "",
        }

        marker = _AlertMarker(alert_id, normalized)
        marker.setPos(scene_x, scene_y)
        self.scene.addItem(marker)
        self.alerts[alert_id] = (marker, None)

    def clear_alerts(self):
        print("[AlertLayer] Clearing all alert markers")
        for marker, _ in self.alerts.values():
            self.scene.removeItem(marker)
        self.alerts.clear()

    def remove_alert(self, alert_id: str):
        """Remove a specific alert marker from the scene."""
        if alert_id not in self.alerts:
            print(f"[AlertLayer] ⚠️ Tried to remove unknown alert_id: {alert_id}")
            return
        marker, _ = self.alerts.pop(alert_id)
        if marker:
            self.scene.removeItem(marker)
        print(f"[AlertLayer] ❌ Removed alert marker: {alert_id}")
