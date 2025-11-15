from PyQt6.QtWidgets import QGraphicsPolygonItem
from PyQt6.QtGui import QColor, QPen, QPolygonF, QBrush
from PyQt6.QtCore import Qt, QPointF
import json
from shapely.geometry import Polygon, box
from shapely.ops import unary_union
from src.vast.orthophoto_canvas.ui.sensors_layer import (
    TILE_SIZE,
    _latlon_to_xy_at_max_zoom,
)


class RegionLayer:
    """Draws farm regions as interactive polygons positioned by GPS coordinates.
       Supports selection by region ID and clips polygons to the orthophoto scene boundaries."""

    def __init__(self, viewer, on_select=None):
        self.viewer = viewer
        self.scene = viewer.scene
        self.regions = []
        self.on_select = on_select

        # Base tile indices at MAX zoom (same as OrthophotoViewer scene)
        z = viewer.max_zoom_fs
        self._x_min_base = viewer.ts.z_ranges[z][0]
        self._y_min_base = viewer.ts.z_ranges[z][2]

        # Scene boundary in scene coordinates (0,0) → (width,height)
        width = (viewer.ts.z_ranges[z][1] - self._x_min_base + 1) * TILE_SIZE
        height = (viewer.ts.z_ranges[z][3] - self._y_min_base + 1) * TILE_SIZE

        self.scene_bounds = box(0, 0, width, height)

    # ─────────────────────────────────────────────
    def add_region(self, region: dict, start_date=None, end_date=None, selected_ids=None):
        """Add a region polygon to the orthophoto map, clipped to scene boundaries."""
        try:
            geom_json = json.loads(region["geom"])
        except Exception as e:
            print(f"[RegionLayer] ❌ Invalid geometry for {region.get('name')}: {e}")
            return

        if not geom_json.get("coordinates"):
            print(f"[RegionLayer] ⚠️ Region {region.get('name')} missing coordinates")
            return

        outer_ring = geom_json["coordinates"][0]
        if len(outer_ring) < 3:
            print(f"[RegionLayer] ⚠️ Region {region.get('name')} has too few points")
            return

        # ── Project region to scene coordinates
        scene_points = []
        for lon, lat in outer_ring:
            pos = _latlon_to_xy_at_max_zoom(self.viewer, lat, lon)
            if not pos:
                continue
            xb, yb = pos
            sx = (xb - self.viewer._x_min_base) * TILE_SIZE
            sy = (yb - self.viewer._y_min_base) * TILE_SIZE
            scene_points.append((sx, sy))

        if len(scene_points) < 3:
            print(f"[RegionLayer] ⚠️ Region {region.get('name')} has too few valid projected points")
            return

        # ── Clip polygon to field boundaries
        poly = Polygon(scene_points)
        clipped = poly.intersection(self.scene_bounds)

        if clipped.is_empty:
            print(f"[RegionLayer] ⚠️ Region {region.get('name')} lies completely outside field, skipped")
            return

        # Merge if multiple fragments (MultiPolygon)
        if clipped.geom_type == "MultiPolygon":
            clipped = unary_union(clipped)

        # ── Convert back to QPolygonF
        def to_qpolygonf(geom):
            """Convert Shapely geometry to QPolygonF (skip LineStrings)."""
            if geom.is_empty:
                return None

            if geom.geom_type == "Polygon":
                pts = [QPointF(x, y) for x, y in geom.exterior.coords]
                return QPolygonF(pts)

            elif geom.geom_type == "MultiPolygon":
                largest = max(geom.geoms, key=lambda g: g.area)
                pts = [QPointF(x, y) for x, y in largest.exterior.coords]
                return QPolygonF(pts)

            print(f"[RegionLayer] ⚠️ Skipped degenerate geometry ({geom.geom_type}) for region {region['name']}")
            return None

        polygon = to_qpolygonf(clipped)
        if not polygon:
            print(f"[RegionLayer] ⚠️ Region {region['name']} clipped to non-polygon shape → skipped")
            return

        # ── Create graphics item
        item = QGraphicsPolygonItem(polygon)
        item.region_id = region["id"]       # ✅ store ID
        item.region_name = region["name"]
        item.selected = False
        item.setZValue(900)

        pen = QPen(QColor("#2563eb"))
        pen.setWidthF(1.5)
        item.setPen(pen)

        # If this region is among pre-selected IDs, fill it stronger
        is_selected = (selected_ids is not None) and (region["id"] in selected_ids)

        base_alpha = 100 if is_selected else 40
        item.setBrush(QColor(37, 99, 235, base_alpha))
        item.selected = bool(is_selected)

        item.setAcceptHoverEvents(True)
        item.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsSelectable, True)

        # Mouse click toggles selection
        item.mousePressEvent = lambda e, it=item: self._toggle_selection(it)
        self.scene.addItem(item)
        self.regions.append(item)

        print(f"[RegionLayer] ✅ Added region '{item.region_name}' (ID {item.region_id}) "
              f"(clipped to {len(clipped.exterior.coords)} vertices)")

    # ─────────────────────────────────────────────
    def _toggle_selection(self, item):
        """Toggle fill color when selected and trigger callback."""
        item.selected = not item.selected
        item.setBrush(QColor(37, 99, 235, 100 if item.selected else 40))

        if self.on_select:
            self.on_select(item.region_id, item.selected)  # ✅ send ID instead of name

    # ─────────────────────────────────────────────
    def clear(self):
        """Remove all region items from the scene."""
        for item in self.regions:
            self.scene.removeItem(item)
        self.regions.clear()
        print("[RegionLayer] Cleared all regions")
        # ─────────────────────────────────────────────
    def setVisible(self, visible: bool):
        """Show or hide all region polygons."""
        for item in self.regions:
            item.setVisible(visible)
        print(f"[RegionLayer] Visibility set to {visible}")

