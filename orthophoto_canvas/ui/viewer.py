# agcloud/ui/viewer.py
from __future__ import annotations
from pathlib import Path
from ..utils.tiles import TileStore

import math
from typing import Iterable, List, Optional, Tuple, Union

from PyQt5.QtCore import Qt, QRectF, QPointF, QTimer
from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor
from PyQt5.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsEllipseItem,
)

# ==== Tunables ====
TILE_SIZE = 512
INITIAL_TILE_PX = 640.0              # initial "tile-size on screen" (px) to compute first zoom
TARGET_TILE_PX_FOR_LOD = 512.0       # target tile size (px) used to pick which z to load
SNAP_CHOICES = (512.0, 384.0, 320.0, 256.0, 192.0, 128.0)  # preferred tile sizes on screen to avoid blur


class OrthophotoViewer(QGraphicsView):
    """
    QGraphicsView that renders a pyramidal tile set with lazy loading + LOD,
    using a provided TileSet (I/O abstraction). Optionally draws sensor markers.
    """

    # ---------- Construction / scene bootstrapping ----------
    def __init__(self, tiles: Union[TileStore, str, Path]) -> None:
        """
        tileset: object that exposes min_zoom, max_zoom, ranges(z), tile_path(z,x,y)
        (see agcloud/io/tileset.py)
        """
        super().__init__()
        if isinstance(tiles, TileStore):
            self.ts = tiles
        else:
            self.ts = TileStore(Path(tiles))

        # שלוף מאפיינים מוכנים מ-TileStore
        self.existing_zooms = self.ts.existing_zooms
        self.min_zoom_fs    = self.ts.min_zoom
        self.max_zoom_fs    = self.ts.max_zoom
        self.z_ranges       = self.ts.z_ranges
        self.is_tms         = self.ts.is_tms


        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        # Crisp rendering (no smoothing)
        self.setRenderHint(QPainter.SmoothPixmapTransform, False)
        self.setRenderHint(QPainter.Antialiasing, False)
        self.setRenderHint(QPainter.TextAntialiasing, False)

        # Interaction / performance
        self.setCacheMode(QGraphicsView.CacheBackground)
        self.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)
        self.setBackgroundBrush(QColor(220, 220, 220))

        # State
        self.current_zoom = self.ts.min_zoom
        self.placeholder_color = Qt.lightGray
        self.tile_items: dict[Tuple[int, int, int], QGraphicsPixmapItem | QGraphicsRectItem] = {}
        self.sensor_items: List[QGraphicsEllipseItem] = []
        self._sensors_mercator: List[Tuple[float, float, dict]] = []  # [(x,y,meta), ...]

        # Debounce loads after interaction
        self.update_timer = QTimer(self)
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_tiles)

        # Scene rect anchored to base zoom (min z)
        self._init_scene_rect_from_min_zoom()

        # Smart initial focus near dataset center at highest z, then snap scale
        found = self._best_focus_tile()  # (z,x,y) close to center
        self._smart_initial_focus(target_tile_px=INITIAL_TILE_PX, found=found, snap=False)
        # self._snap_to_native_scale()

        # First load
        self.update_tiles()

    def _init_scene_rect_from_min_zoom(self) -> None:
        """
        Build scene rect from the min zoom range (anchor for all z levels).
        """
        z0 = self.ts.min_zoom
        x_min, x_max, y_min, y_max = self.ts.z_ranges[z0]
        width = (x_max - x_min + 1) * TILE_SIZE
        height = (y_max - y_min + 1) * TILE_SIZE
        self._x_min_base = x_min
        self._y_min_base = y_min
        self.scene.setSceneRect(0, 0, width, height)
        print(f"[BASE] z={z0} X:[{x_min}-{x_max}] Y:[{y_min}-{y_max}] scene={width}x{height}px")

    # ---------- Sensors overlay (optional) ----------
    def set_sensors(self, sensors_mercator: Iterable[Tuple[float, float, dict]], radius_px: int = 5) -> None:
        """
        Provide sensors as iterable of (X_3857, Y_3857, meta_dict).
        They will be reprojected to tile-indices on the fly and drawn as small circles.
        """
        self._sensors_mercator = list(sensors_mercator)
        self._sensor_radius = max(1, int(radius_px))
        self._rebuild_sensor_items()  # build once; position is updated when zoom/scroll changes

    def clear_sensors(self) -> None:
        """Remove all sensor markers from scene."""
        for it in self.sensor_items:
            self.scene.removeItem(it)
        self.sensor_items.clear()
        self._sensors_mercator.clear()

    def _rebuild_sensor_items(self) -> None:
        """(Re)create QGraphicsEllipseItem for each sensor (positions updated in _update_sensor_positions)."""
        for it in self.sensor_items:
            self.scene.removeItem(it)
        self.sensor_items.clear()

        # create items (position later)
        for _ in self._sensors_mercator:
            it = QGraphicsEllipseItem(0, 0, self._sensor_radius * 2, self._sensor_radius * 2)
            it.setBrush(QColor(200, 40, 40))
            it.setPen(QPen(Qt.NoPen))
            it.setZValue(1000)  # above tiles
            self.scene.addItem(it)
            self.sensor_items.append(it)

        self._update_sensor_positions()

    def _update_sensor_positions(self) -> None:
        """
        Convert 3857 coords → scene pixels via z_base anchoring.
        We need an affine mapping from mercator meters to tile indices at min z.
        For simplicity, we derive it from the tile grid at min z.
        """
        if not self._sensors_mercator:
            return

        z0 = self.ts.min_zoom
        x_min, x_max, y_min, y_max = self.ts.ranges(z0)

        # Take two reference tiles to estimate mercator extent spanned by [x_min..x_max],[y_min..y_max]
        # Tile bounds in mercator for XYZ at (z0, x, y):
        def xyz_tile_bounds_merc(z: int, x: int, y: int) -> Tuple[float, float, float, float]:
            # WebMercator meters
            TILE_WORLD_SIZE = 2 * math.pi * 6378137.0
            n = 1 << z
            tile_span_m = TILE_WORLD_SIZE / n
            # origin x=-half, y=+half (top), y grows down in tiles; real mercator Y grows up, so flip
            x0 = -TILE_WORLD_SIZE / 2 + x * tile_span_m
            y0_top = +TILE_WORLD_SIZE / 2 - y * tile_span_m
            return (x0, y0_top - tile_span_m, x0 + tile_span_m, y0_top)

        # overall mercator bbox at min z (rough, sufficient for placing points)
        x0_w, y0_s, x0_e, y0_n = xyz_tile_bounds_merc(z0, x_min, y_min)
        x1_w, y1_s, x1_e, y1_n = xyz_tile_bounds_merc(z0, x_max + 1, y_max + 1)
        merc_left, merc_right = x0_w, x1_e
        merc_top, merc_bottom = y0_n, y1_s  # note: top > bottom in merc meters

        width_scene = (x_max - x_min + 1) * TILE_SIZE
        height_scene = (y_max - y_min + 1) * TILE_SIZE

        def to_scene(x_m: float, y_m: float) -> Tuple[float, float]:
            # map mercator to scene rect anchored at min z
            sx = (x_m - merc_left) / (merc_right - merc_left) * width_scene
            sy = (merc_top - y_m) / (merc_top - merc_bottom) * height_scene
            return sx, sy

        for (idx, (mx, my, _meta)) in enumerate(self._sensors_mercator):
            sx, sy = to_scene(mx, my)
            it = self.sensor_items[idx]
            it.setPos(sx - self._sensor_radius, sy - self._sensor_radius)

    # ---------- Interaction ----------
    def wheelEvent(self, event) -> None:
        factor = 1.25
        if event.angleDelta().y() > 0:
            self.scale(factor, factor)
        else:
            self.scale(1.0 / factor, 1.0 / factor)
        self._debounced_update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._debounced_update()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if event.button() in (Qt.LeftButton, Qt.MiddleButton):
            self._debounced_update()

    def keyPressEvent(self, event) -> None:
        k = event.key()
        if k == Qt.Key_C:
            self._snap_to_native_scale()
            return
        if k == Qt.Key_F:
            self._fit_data_width()
            return
        if k in (Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5):
            choices = {
                Qt.Key_1: 192.0,
                Qt.Key_2: 256.0,
                Qt.Key_3: 320.0,
                Qt.Key_4: 384.0,
                Qt.Key_5: 512.0,
            }
            self._smart_initial_focus(target_tile_px=choices[k], found=self._best_focus_tile())
            return
        super().keyPressEvent(event)

    def _debounced_update(self) -> None:
        self.update_timer.start(50)

    def showEvent(self, e):
        """ברגע שהחלון מוצג, נתאים מיד את הזום כדי שיראו גדול."""
        super().showEvent(e)
        QTimer.singleShot(0, lambda: self.fit_to_data("width", 0.98))

    # ---------- LOD: choose z, load visible tiles ----------
    def _calc_zoom_level(self) -> int:
        """
        Decide which z to load: pick z so that (tile on screen) ~= TARGET_TILE_PX_FOR_LOD.
        """
        scale = max(self.transform().m11(), 1e-6)
        z_base = self.ts.min_zoom
        zf = z_base + math.log2((scale * float(TILE_SIZE)) / TARGET_TILE_PX_FOR_LOD)
        z = int(round(zf))
        return max(self.ts.min_zoom, min(self.ts.max_zoom, z))

    def update_tiles(self) -> None:
        """
        Core: compute visible keys (z,x,y) and ensure each has an item.
        Placeholders are created first; then upgraded to true pixmaps (with parent fallback).
        """
        # update sensor overlay position (cheap)
        self._update_sensor_positions()

        z = self._calc_zoom_level()
        self.current_zoom = z

        eff_tile_scene = TILE_SIZE / float(1 << (z - self.ts.min_zoom))
        eff_tile_screen = eff_tile_scene * max(self.transform().m11(), 1e-6)
        print(f"[LODDBG] z={z} tile_on_screen≈{eff_tile_screen:.1f}px")

        view_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        x_min_z, x_max_z, y_min_z, y_max_z = self.ts.z_ranges[z]

        # scene → base indices (anchored to min z)
        start_tx = int(math.floor(view_rect.left()   / eff_tile_scene))
        end_tx   = int(math.floor(view_rect.right()  / eff_tile_scene))
        start_ty = int(math.floor(view_rect.top()    / eff_tile_scene))
        end_ty   = int(math.floor(view_rect.bottom() / eff_tile_scene))

        scale_factor = 1 << (z - self.ts.min_zoom)
        want: set[Tuple[int, int, int]] = set()
        for tx in range(start_tx, end_tx + 1):
            for ty in range(start_ty, end_ty + 1):
                x_idx = self._x_min_base * scale_factor + tx
                y_idx = self._y_min_base * scale_factor + ty
                # clamp to existing range on disk
                if x_idx < x_min_z or x_idx > x_max_z or y_idx < y_min_z or y_idx > y_max_z:
                    continue
                want.add((z, x_idx, y_idx))

        # Create / upgrade
        for key in want:
            if key not in self.tile_items:
                ph = self._create_placeholder_item_at(key, eff_tile_scene)
                self.tile_items[key] = ph
                self.scene.addItem(ph)
                self._try_upgrade_tile_to_pixmap(key, eff_tile_scene)

        # Unload others
        for key in list(self.tile_items.keys()):
            if key not in want:
                self.scene.removeItem(self.tile_items.pop(key))

    # ---------- Tile placement / upgrade ----------
    def _create_placeholder_item_at(self, key: Tuple[int, int, int], eff_tile_scene: float):
        """
        Create a light-gray rect exactly where the tile will go (no rounding) to avoid seams.
        """
        z, x, y = key
        scale_factor = 1 << (z - self.ts.min_zoom)
        x0 = self._x_min_base * scale_factor
        y0 = self._y_min_base * scale_factor

        tx = x - x0
        ty = y - y0
        sx = tx * eff_tile_scene
        sy = ty * eff_tile_scene

        rect = QGraphicsRectItem(sx, sy, eff_tile_scene, eff_tile_scene)
        rect.setBrush(self.placeholder_color)
        rect.setPen(QPen(Qt.NoPen))
        return rect

    def _place_pixmap_item(self, pm: QPixmap, key: Tuple[int, int, int], eff_tile_scene: float):
        """
        Position the pixmap at exact scene coords (anchored to min z) and scale the item,
        not the pixmap (keeps the source un-resampled).
        """
        z, x, y = key
        scale_factor = 1 << (z - self.ts.min_zoom)
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
        item.setTransformationMode(Qt.FastTransformation)
        return item

    def _try_upgrade_tile_to_pixmap(self, key: Tuple[int, int, int], eff_tile_scene: float) -> None:
        """
        Replace placeholder by the right pixmap:
        - Try native z/x/y
        - If missing, climb to parent(s) until min z, crop the relevant quadrant.
        """
        z, x, y = key

        # climb parents if needed
        zz, xx, yy = z, x, y
        pm: Optional[QPixmap] = None
        while zz >= self.ts.min_zoom:
            p = self.ts.tile_path(zz, xx, yy)
            if p:
                pm0 = QPixmap(p)
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
            xx //= 2; yy //= 2; zz -= 1

        if not pm:
            return

        old = self.tile_items.get(key)
        if old:
            self.scene.removeItem(old)
        item = self._place_pixmap_item(pm, key, eff_tile_scene)
        self.scene.addItem(item)
        self.tile_items[key] = item

    # ---------- Smart focus / fit / snap ----------
    def _smart_initial_focus(self, target_tile_px: float, found: Optional[Tuple[int, int, int]], snap=True) -> None:
        """
        Pick a zoom/transform so that one tile would appear ~target_tile_px wide on screen,
        and center the view around an existing tile (found).
        """
        if not found:
            # fallback: fit entire base scene width
            self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)
            return

        z, x, y = found
        eff_scene = TILE_SIZE / float(1 << (z - self.ts.min_zoom))
        s = max(target_tile_px / eff_scene, 1e-6)

        self.resetTransform()
        self.scale(s, s)

        if snap:
            self._snap_to_native_scale()

        # center on that tile
        scale_factor = 1 << (z - self.ts.min_zoom)
        x0 = self._x_min_base * scale_factor
        y0 = self._y_min_base * scale_factor
        tx = x - x0
        ty = y - y0
        sx = tx * eff_scene
        sy = ty * eff_scene
        self.centerOn(sx + eff_scene * 0.5, sy + eff_scene * 0.5)

        self._debounced_update()
        print(f"[FOCUS] center @ {z}/{x}/{y} tile≈{target_tile_px:.0f}px")

    def _snap_to_native_scale(self) -> None:
        """
        Snap current transform so that tile size on screen equals one of SNAP_CHOICES,
        minimizing resampling blur.
        """
        center_scene = self.mapToScene(self.viewport().rect().center())
        z = self._calc_zoom_level()
        eff_scene = TILE_SIZE / float(1 << (z - self.ts.min_zoom))
        cur_tile = eff_scene * max(self.transform().m11(), 1e-6)
        target = min(SNAP_CHOICES, key=lambda t: abs(t - cur_tile))
        s = max(target / eff_scene, 1e-6)
        self.resetTransform()
        self.scale(s, s)
        self.centerOn(center_scene)
        self._debounced_update()

    def _fit_data_width(self, margin: float = 0.95) -> None:
        """
        Fit the visible data extent at current z to the viewport width (keep slight margin).
        """
        z = self._calc_zoom_level()
        x_min, x_max, y_min, y_max = self.ts.z_ranges[z]
        eff = TILE_SIZE / float(1 << (z - self.ts.min_zoom))

        scale_factor = 1 << (z - self.ts.min_zoom)
        x0 = self._x_min_base * scale_factor
        y0 = self._y_min_base * scale_factor

        left   = (x_min - x0) * eff
        right  = (x_max - x0 + 1) * eff
        top    = (y_min - y0) * eff
        bottom = (y_max - y0 + 1) * eff
        rect = QRectF(left, top, right - left, bottom - top)

        self.resetTransform()
        if rect.width() > 0:
            s_w = (self.viewport().width() / rect.width()) * float(margin)
            self.scale(s_w, s_w)
            self.centerOn(rect.center())
            self._debounced_update()
            print(f"[FIT] width={rect.width():.1f}px scene, scale={s_w:.3f}")

    def fit_to_data(self, how="width", margin=0.98):
        """Zoom so the dataset fills the viewport (width/height/all)."""
        z = self._calc_zoom_level()
        self.current_zoom_level = z
        if z not in self.z_ranges:
            return

        x_min_z, x_max_z, y_min_z, y_max_z = self.z_ranges[z]

        eff = TILE_SIZE / float(1 << (z - self.min_zoom_fs))

        base_x_min, _, base_y_min, _ = self.z_ranges[self.min_zoom_fs]
        scale_factor = 1 << (z - self.min_zoom_fs)
        x0 = base_x_min * scale_factor
        y0 = base_y_min * scale_factor


        left   = (x_min_z - x0) * eff
        top    = (y_min_z - y0) * eff
        width  = (x_max_z - x_min_z + 1) * eff
        height = (y_max_z - y_min_z + 1) * eff
        rect = QRectF(left, top, width, height)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        self.resetTransform()
        if how == "width":
            s = (self.viewport().width() / rect.width()) * margin
        elif how == "height":
            s = (self.viewport().height() / rect.height()) * margin
        else:  # "all"
            s = min(self.viewport().width()/rect.width(),
                    self.viewport().height()/rect.height()) * margin

        self.scale(s, s)
        self.centerOn(rect.center())
        self._debounced_update()

    # ---------- Find a good starting tile ----------
    def _best_focus_tile(self, prefer_z: Optional[int] = None, max_x_check: int = 64) -> Optional[Tuple[int,int,int]]:
        """
        Heuristic: at the highest available z, choose x that is closest to mid-range,
        then choose the y closest to mid-range that actually exists. If that x has no y,
        try other x (still ordered by proximity to center). If nothing found, fall back to
        the first available (z,x,y).
        """
        zs = list(range(self.ts.min_zoom, self.ts.max_zoom + 1))
        if not zs:
            return None
        z = prefer_z if prefer_z is not None else zs[-1]

        try:
            x_min, x_max, y_min, y_max = self.ts.ranges(z)
        except Exception:
            return None

        x0 = (x_min + x_max) // 2
        y0 = (y_min + y_max) // 2

        # Prefer X near the center
        xs = list(range(x_min, x_max + 1))
        xs.sort(key=lambda xv: abs(xv - x0))

        # helper to list ys for an x (if tileset doesn’t implement list_y, we try a few probes)
        def list_y_for_x(x: int) -> List[int]:
            if hasattr(self.ts, "list_y"):
                return list(getattr(self.ts, "list_y")(z, x))  # type: ignore
            # minimal probe: try a small window around y0
            win = 256
            candidates = []
            for yy in (y0, y0-1, y0+1, y0-2, y0+2, y0-4, y0+4, y0-win, y0+win):
                p = self.ts.tile_path(z, x, yy)
                if p:
                    candidates.append(yy)
            return sorted(set(candidates))

        # Try up to max_x_check x-folders near center
        for x in xs[:max_x_check]:
            ys = list_y_for_x(x)
            if not ys:
                continue
            y = min(ys, key=lambda yv: abs(yv - y0))
            return (z, x, y)

        # Fallback: brute probe a small grid near center
        for x in xs:
            for y in (y0, y0-1, y0+1, y0-2, y0+2):
                if self.ts.tile_path(z, x, y):
                    return (z, x, y)

        # Last resort: scan all ranges (can be slower on huge sets)
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                if self.ts.tile_path(z, x, y):
                    return (z, x, y)

        return None
