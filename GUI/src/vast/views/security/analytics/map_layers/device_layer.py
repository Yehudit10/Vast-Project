from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt
from src.vast.orthophoto_canvas.ui.sensors_layer import TILE_SIZE, _latlon_to_xy_at_max_zoom

from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsDropShadowEffect, QGraphicsColorizeEffect
from PyQt6.QtGui import QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve


# ─────────────────────────────────────────────
# 🗺️ Device Layer
# ─────────────────────────────────────────────
class DeviceLayer:
    """Draws device (camera) markers on the orthophoto scene."""

    def __init__(self, viewer, on_select=None):
        self.viewer = viewer
        self.scene = viewer.scene
        self.devices = {}
        self.on_select = on_select

        # Match RegionLayer & AlertLayer → use MAX zoom base tiles
        z = viewer.max_zoom_fs
        self._x_min_base = viewer.ts.z_ranges[z][0]
        self._y_min_base = viewer.ts.z_ranges[z][2]

    def add_device(self, device: dict, start_date=None, end_date=None, selected=False):

        """Add a device marker to the orthophoto scene."""
        lat = device.get("location_lat")
        lon = device.get("location_lon")

        # Convert to base XY in max zoom coordinate space
        pos = _latlon_to_xy_at_max_zoom(self.viewer, lat, lon)
        if not pos:
            print(f"[DeviceLayer] ⚠️ Device {device.get('device_id')} outside field bounds")
            return

        xb, yb = pos
        scene_x = (xb - self._x_min_base) * TILE_SIZE
        scene_y = (yb - self._y_min_base) * TILE_SIZE
        marker = _Camera360Marker(
            device["device_id"],
            device.get("active", True),
            self.on_select,
            radius=10.0,  # tweak for size
        )
        marker.setPos(scene_x, scene_y)
        self.scene.addItem(marker)

        self.devices[device["device_id"]] = marker

        if selected:
            marker.selected = True
            marker.setFont(QFont("Noto Color Emoji", 18))
            marker.setDefaultTextColor(marker.selected_color)
            marker.setGraphicsEffect(marker.halo)
            marker.pulse.start()

        print(f"[DeviceLayer] ✅ Added device '{device['device_id']}' at ({scene_x:.1f}, {scene_y:.1f})")

    def clear(self):
        """Remove all device markers."""
        for item in self.devices.values():
            self.scene.removeItem(item)
        self.devices.clear()
        print("[DeviceLayer] Cleared all devices")
    def setVisible(self, visible: bool):
        """Show or hide all device markers."""
        for item in self.devices.values():
            item.setVisible(visible)
        print(f"[DeviceLayer] Visibility set to {visible}")
from PyQt6.QtWidgets import QGraphicsObject, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter
from PyQt6.QtCore import QRectF, QPropertyAnimation, QEasingCurve, pyqtSlot


class _Camera360Marker(QGraphicsObject):
    """360° camera marker: donut + center dot + glow + pulse."""

    def __init__(self, device_id: str, active: bool, on_select=None, radius: float = 10.0):
        super().__init__()
        self.device_id = device_id
        self.active = active
        self.on_select = on_select
        self.selected = False
        self._radius = radius

        # Colors
        self.normal_color = QColor("#10b981") if active else QColor("#9ca3af")   # green / gray
        self.alert_color = QColor("#ef4444")                                     # red for alerts if you use it
        self.selected_color = QColor("#ffffff")

        # We draw in local coords around (0,0); QGraphicsView will position us
        self.setZValue(1000)
        self.setFlag(self.GraphicsItemFlag.ItemIgnoresTransformations, True)  # stay same size on zoom
        self.setAcceptHoverEvents(True)

        # Drop shadow halo for glow
        self.halo = QGraphicsDropShadowEffect()
        self.halo.setBlurRadius(32)
        self.halo.setOffset(0, 0)
        self.halo.setColor(QColor(16, 185, 129, 180))
        self.setGraphicsEffect(None)  # only on selection

        # Pulse animation on opacity
        self.pulse = QPropertyAnimation(self, b"opacity")
        self.pulse.setDuration(1000)
        self.pulse.setStartValue(1.0)
        self.pulse.setEndValue(0.6)
        self.pulse.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.pulse.setLoopCount(-1)

    # ─────────────────────────────────────────────
    # Required overrides
    # ─────────────────────────────────────────────
    def boundingRect(self) -> QRectF:
        # a bit larger than radius to accommodate the stroke + halo
        r = self._radius + 4
        return QRectF(-r, -r, 2 * r, 2 * r)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # Base color depends on state
        base = self.normal_color if not self.selected else self.normal_color

        # Outer ring (donut)
        outer_r = self._radius
        inner_r = self._radius * 0.55

        # Outer circle stroke
        pen = QPen(base)
        pen.setWidthF(2.0 if not self.selected else 3.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(-outer_r, -outer_r, 2 * outer_r, 2 * outer_r))

        # Soft filled ring (semi-transparent)
        ring_color = QColor(base.red(), base.green(), base.blue(), 80)
        painter.setBrush(QBrush(ring_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(-outer_r, -outer_r, 2 * outer_r, 2 * outer_r))

        # Cut inner circle to make donut effect (by drawing a solid inner circle of background color)
        inner_bg = QColor("#0f172a")  # same tone as map background / dark outline
        painter.setBrush(inner_bg)
        painter.drawEllipse(QRectF(-inner_r, -inner_r, 2 * inner_r, 2 * inner_r))

        # Center dot – represents the physical camera
        center_r = inner_r * 0.5
        painter.setBrush(base if not self.selected else self.selected_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(-center_r, -center_r, 2 * center_r, 2 * center_r))

    # ─────────────────────────────────────────────
    # Interaction
    # ─────────────────────────────────────────────
    def mousePressEvent(self, event):
        self.toggle_selected()
        if self.on_select:
            self.on_select(self.device_id, self.selected)
        super().mousePressEvent(event)

    @pyqtSlot()
    def toggle_selected(self):
        self.selected = not self.selected

        if self.selected:
            # enable glow + pulse
            self.setGraphicsEffect(self.halo)
            self.pulse.start()
        else:
            # disable glow + pulse
            self.setGraphicsEffect(None)
            self.pulse.stop()
            self.setOpacity(1.0)
        self.update()
