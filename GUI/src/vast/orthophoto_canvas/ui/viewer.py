from __future__ import annotations
from pathlib import Path
from ..utils.tiles import TileStore
from .sensors_layer import SensorLayer, add_sensors_by_gps_bulk, dataset_bbox_latlon
from ..ag_io.sensors_api import get_sensors

import math
from typing import Optional, Tuple, Union

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QGraphicsRectItem
)
from PyQt6.QtGui import QPixmap, QTransform
# ==== Tunables ====
TILE_SIZE = 512
TARGET_TILE_PX_FOR_LOD = 512.0
SNAP_CHOICES = (512.0, 384.0, 320.0, 256.0, 192.0, 128.0)


class OrthophotoViewer(QGraphicsView):
    """Stable orthophoto tile viewer that perfectly fits its container."""

    def __init__(self, tiles: Union[TileStore, str, Path]) -> None:
        super().__init__()

      
        # ─────────────────────────────
# Load tiles
# ─────────────────────────────
        if isinstance(tiles, TileStore):
            self.ts = tiles
        else:
            tiles_path = Path(tiles)
            if not tiles_path.exists():
                raise FileNotFoundError(f"[OrthophotoViewer] Tile root not found: {tiles_path}")
            self.ts = TileStore(tiles_path)

        # Safety: ensure scheme attribute exists
        if not hasattr(self.ts, "scheme"):
            self.ts.scheme = "XYZ"

        self.min_zoom_fs = self.ts.min_zoom
        self.max_zoom_fs = self.ts.max_zoom
        self.z_ranges = self.ts.z_ranges
        self.is_tms = self.ts.is_tms

        print(f"[DEBUG] Tile root: {self.ts.root}")
        print(f"[DEBUG] Tile scheme: {self.ts.scheme}")
        print(f"[DEBUG] is_tms: {self.ts.is_tms}")
        print(f"[DEBUG] Zoom levels: {self.ts.existing_zooms or 'none found'}")
        print(f"[DEBUG] z_ranges: {self.ts.z_ranges or 'empty'}")

        


        # ─────────────────────────────
        # Scene setup
        # ─────────────────────────────
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)

        # 🔹 Light gray background (no border)
        self.setBackgroundBrush(QColor("#d1d5db"))  # soft gray background
        self.setStyleSheet("background-color: #d1d5db; border: none;")

        # No scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # ─────────────────────────────
        # Internal state
        # ─────────────────────────────
        self.current_zoom = self.ts.max_zoom
        self.placeholder_color = QColor("#d1d5db")
        self.tile_items: dict[Tuple[int, int, int], QGraphicsPixmapItem | QGraphicsRectItem] = {}

        # ─────────────────────────────
        # Timed updates
        # ─────────────────────────────
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_tiles)

        # ─────────────────────────────
        # Optional sensor overlay
        # ─────────────────────────────
        self.sensor_layer = SensorLayer(self)
        dataset_bbox_latlon(self, z=self.max_zoom_fs)
        
        try:
            add_sensors_by_gps_bulk(self.sensor_layer, get_sensors(), z=self.max_zoom_fs, default_radius_px=0.2)
        except Exception as e:
            print(f"[Sensors] skipped: {e}")

        # ─────────────────────────────
        # Scene geometry from MAX zoom
        # ─────────────────────────────
        self._init_scene_rect_from_max_zoom()

        # ─────────────────────────────
        # Initial zoom and centering
        # ─────────────────────────────
        self._fit_scene_exactly()

        # ─────────────────────────────
        # Initial tile rendering
        # ─────────────────────────────
        self._custom_bg_item: Optional[QGraphicsPixmapItem] = None
        self._tiles_visible: bool = True
        self.update_tiles()

    def _apply_tile_visibility(self):
        """Apply visibility/opacity preference to existing tile items."""
        for item in self.tile_items.values():
            # You can choose to hide or fade; here we just hide/show them.
            item.setVisible(self._tiles_visible)
            # If you prefer fading:
            # item.setOpacity(0.2 if not self._tiles_visible else 1.0)

    

    def set_custom_background_image(self, path: str, hide_tiles: bool = False):
        """
        Place a single static image as the map background, scaled to the scene extents.
        It will zoom & pan together with all other items.
        """
        pix = QPixmap(path)
        p = Path(path)
        print("[OrthophotoViewer] Exists?", p.exists())
        if pix.isNull():
            print(f"[OrthophotoViewer] ❌ Failed to load background image: {path}")
            return

        # Remove previous bg if exists
        if self._custom_bg_item is not None:
            self.scene.removeItem(self._custom_bg_item)
            self._custom_bg_item = None

        scene_rect = self.scene.sceneRect()
        width = scene_rect.width()
        height = scene_rect.height()

        item = QGraphicsPixmapItem(pix)
        item.setZValue(-1000)  # behind tiles, regions, sensors

        # Scale to fill the entire scene rect
        sx = width / pix.width() if pix.width() > 0 else 1.0
        sy = height / pix.height() if pix.height() > 0 else 1.0
        item.setTransform(QTransform().scale(sx, sy))

        # Position at the scene rect origin (you use a small margin, so respect that)
        item.setPos(scene_rect.left(), scene_rect.top())

        self.scene.addItem(item)
        self._custom_bg_item = item

        if hide_tiles:
            self._tiles_visible = False
            self._apply_tile_visibility()

    # ─────────────────────────────
    # Scene geometry
    # ─────────────────────────────
    def _init_scene_rect_from_max_zoom(self) -> None:
        """Build scene rect from the max zoom level (actual dataset size)."""
        z_max = self.ts.max_zoom
        x_min, x_max, y_min, y_max = self.ts.z_ranges[z_max]
        width = (x_max - x_min + 1) * TILE_SIZE
        height = (y_max - y_min + 1) * TILE_SIZE
        self._x_min_base = x_min
        self._y_min_base = y_min

        # Add tiny margin to prevent borders
        margin = 2
        self.scene.setSceneRect(-margin, -margin, width + margin * 2, height + margin * 2)
        print(f"[BASE] z={z_max} scene={width}x{height}px")

    # ─────────────────────────────
    # Fit helper
    # ─────────────────────────────
    def _fit_scene_exactly(self):
        """Reset zoom and fit map exactly to the view size."""
        self.resetTransform()
        self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.centerOn(self.scene.sceneRect().center())

    # ─────────────────────────────
    # Events
    # ─────────────────────────────
    def resizeEvent(self, e):
        """Fit perfectly when resized, no cumulative zoom."""
        super().resizeEvent(e)
        self._fit_scene_exactly()
        self._debounced_update()


    def wheelEvent(self, event) -> None:
        """Zoom with mouse wheel."""
        factor = 1.25
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1.0 / factor, 1.0 / factor)
        self._debounced_update()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._debounced_update()

    def _debounced_update(self) -> None:
        self.update_timer.start(50)

    # ─────────────────────────────
    # Level-of-detail (LOD)
    # ─────────────────────────────
    def _calc_zoom_level(self) -> int:
        """Force max zoom for small coverage sets."""
        return self.ts.max_zoom

    def update_tiles(self) -> None:
        """Compute visible tiles and render them."""
        z = self._calc_zoom_level()
        self.current_zoom = z

        eff_tile_scene = TILE_SIZE / float(1 << (z - self.ts.max_zoom))
        eff_tile_screen = eff_tile_scene * max(self.transform().m11(), 1e-6)
        print(f"[LODDBG] z={z} tile_on_screen≈{eff_tile_screen:.1f}px")

        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        x_min_z, x_max_z, y_min_z, y_max_z = self.ts.z_ranges[z]

        start_tx = int(math.floor(view_rect.left() / eff_tile_scene))
        end_tx = int(math.floor(view_rect.right() / eff_tile_scene))
        start_ty = int(math.floor(view_rect.top() / eff_tile_scene))
        end_ty = int(math.floor(view_rect.bottom() / eff_tile_scene))

        scale_factor = 1 << (z - self.ts.max_zoom)
        want: set[Tuple[int, int, int]] = set()
        for tx in range(start_tx, end_tx + 1):
            for ty in range(start_ty, end_ty + 1):
                x_idx = self._x_min_base * scale_factor + tx
                y_idx = self._y_min_base * scale_factor + ty
                if x_idx < x_min_z or x_idx > x_max_z or y_idx < y_min_z or y_idx > y_max_z:
                    continue
                want.add((z, x_idx, y_idx))

        # Create or upgrade
        for key in want:
            if key not in self.tile_items:
                ph = self._create_placeholder_item_at(key, eff_tile_scene)
                self.tile_items[key] = ph
                self.scene.addItem(ph)
                self._try_upgrade_tile_to_pixmap(key, eff_tile_scene)

        # Unload tiles that are no longer visible
        for key in list(self.tile_items.keys()):
            if key not in want:
                self.scene.removeItem(self.tile_items.pop(key))

        # 🔹 Ensure visibility style is applied to all tiles (including new ones)
        self._apply_tile_visibility()

    # ─────────────────────────────
    # Tile placement / upgrade
    # ─────────────────────────────
    def _create_placeholder_item_at(self, key: Tuple[int, int, int], eff_tile_scene: float):
        z, x, y = key
        scale_factor = 1 << (z - self.ts.max_zoom)
        x0 = self._x_min_base * scale_factor
        y0 = self._y_min_base * scale_factor
        tx = x - x0
        ty = y - y0
        sx = tx * eff_tile_scene
        sy = ty * eff_tile_scene

        rect = QGraphicsRectItem(sx, sy, eff_tile_scene, eff_tile_scene)
        rect.setBrush(QColor("#d1d5db"))  # same gray as background
        rect.setPen(QPen(Qt.PenStyle.NoPen))
        return rect

    def _place_pixmap_item(self, pm: QPixmap, key: Tuple[int, int, int], eff_tile_scene: float):
        z, x, y = key
        scale_factor = 1 << (z - self.ts.max_zoom)
        x0 = self._x_min_base * scale_factor
        y0 = self._y_min_base * scale_factor
        tx = x - x0
        ty = y - y0
        sx = tx * eff_tile_scene
        sy = ty * eff_tile_scene

        item = QGraphicsPixmapItem(pm)
        item.setPos(sx, sy)
        s = eff_tile_scene / float(pm.width())
        item.setScale(s)
        item.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        return item

    def _try_upgrade_tile_to_pixmap(self, key: Tuple[int, int, int], eff_tile_scene: float) -> None:
        z, x, y = key
        # print(f"[TRY] tile z={z} x={x} y={y}")
        zz, xx, yy = z, x, y
        pm: Optional[QPixmap] = None
        while zz >= self.ts.min_zoom:
            p = self.ts.tile_path(zz, xx, yy)
            if p:
                pm0 = QPixmap(str(p))
                if not pm0.isNull():
                    pm = pm0
                    if zz < z:
                        k = z - zz
                        seg = 1 << k
                        w = pm.width() // seg
                        h = pm.height() // seg
                        u = (x % seg) * w
                        v = (y % seg) * h
                        pm = pm.copy(u, v, w, h)
                    break
            xx //= 2
            yy //= 2
            zz -= 1

        if not pm:
            return

        old = self.tile_items.get(key)
        if old:
            self.scene.removeItem(old)
        item = self._place_pixmap_item(pm, key, eff_tile_scene)
        self.scene.addItem(item)
        self.tile_items[key] = item
