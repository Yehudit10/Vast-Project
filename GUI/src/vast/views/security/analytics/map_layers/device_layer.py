from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsDropShadowEffect
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtCore import Qt
from src.vast.orthophoto_canvas.ui.sensors_layer import TILE_SIZE, _latlon_to_xy_at_max_zoom

from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsDropShadowEffect, QGraphicsColorizeEffect
from PyQt6.QtGui import QColor, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve


class _DeviceMarker(QGraphicsTextItem):
    """A single camera/device emoji marker with selection halo and pulse effect."""

    def __init__(self, device_id: str, active: bool, on_select=None):
        super().__init__("📷")
        self.device_id = device_id
        self.active = active
        self.on_select = on_select
        self.selected = False

        # Base style — emoji, color by status
        self.normal_color = QColor("#10b981") if active else QColor("#9ca3af")
        self.selected_color = QColor("#ffffff")
        self.setFont(QFont("Noto Color Emoji", 14))
        self.setDefaultTextColor(self.normal_color)
        self.setZValue(1000)
        self.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setAcceptHoverEvents(True)

        # Halo effect for glow
        self.halo = QGraphicsDropShadowEffect()
        self.halo.setBlurRadius(40)
        self.halo.setOffset(0, 0)
        self.halo.setColor(QColor(16, 185, 129, 160))
        self.setGraphicsEffect(None)

        # Pulse animation
        self.pulse = QPropertyAnimation(self, b"opacity")
        self.pulse.setDuration(1000)
        self.pulse.setStartValue(1.0)
        self.pulse.setEndValue(0.5)
        self.pulse.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.pulse.setLoopCount(-1)

    def mousePressEvent(self, event):
        """Toggle selection highlight and trigger callback."""
        self.selected = not self.selected

        if self.selected:
            self.setFont(QFont("Noto Color Emoji", 18))
            self.setDefaultTextColor(self.selected_color)
            self.halo.setColor(QColor(5, 150, 105, 255))
            self.setGraphicsEffect(self.halo)
            self.pulse.start()
        else:
            self.setFont(QFont("Noto Color Emoji", 14))
            self.setDefaultTextColor(self.normal_color)
            self.setGraphicsEffect(None)
            self.pulse.stop()
            self.setOpacity(1.0)

        if self.on_select:
            self.on_select(self.device_id, self.selected)

        super().mousePressEvent(event)
        # ─────────────────────────────────────────────
    




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

        marker = _DeviceMarker(device["device_id"], device.get("active", True), self.on_select)
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
