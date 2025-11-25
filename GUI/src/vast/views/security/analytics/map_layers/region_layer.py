from __future__ import annotations

import json
from typing import List, Optional, Tuple

from PyQt6.QtWidgets import QGraphicsPolygonItem
from PyQt6.QtGui import QColor, QPen, QPolygonF
from PyQt6.QtCore import Qt, QPointF

from src.vast.orthophoto_canvas.ui.sensors_layer import (
    TILE_SIZE,
    _latlon_to_xy_at_max_zoom,
)


class RegionLayer:
    """
    Draws farm regions as interactive polygons positioned by GPS coordinates.
    Uses tile-based projection when possible, and falls back to a linear
    lon/lat → scene mapping based on the known map coverage if needed.
    """

    def __init__(self, viewer, on_select=None):
        self.viewer = viewer
        self.scene = viewer.scene
        self.regions: List[QGraphicsPolygonItem] = []
        self.on_select = on_select

        # Base tile indices at MAX zoom (same as OrthophotoViewer scene)
        z = viewer.max_zoom_fs
        self._x_min_base = viewer.ts.z_ranges[z][0]
        self._y_min_base = viewer.ts.z_ranges[z][2]

        # Scene boundary in scene coordinates (0,0) → (width,height)
        width = (viewer.ts.z_ranges[z][1] - self._x_min_base + 1) * TILE_SIZE
        height = (viewer.ts.z_ranges[z][3] - self._y_min_base + 1) * TILE_SIZE
        self._scene_width = width
        self._scene_height = height

        # For reference; not used for clipping anymore
        self.scene_bounds = (0, 0, width, height)

        # 🔹 Map lon/lat bounds – SAME as you used in your SQL
        #   [COVERAGE z=18] lon:[34.844513..34.855499]  lat:[31.895049..31.904376]
        self._map_min_lon = 34.844513
        self._map_max_lon = 34.855499
        self._map_min_lat = 31.895049
        self._map_max_lat = 31.904376

    # ─────────────────────────────────────────────
    # Helper: robust projection
    # ─────────────────────────────────────────────
    def _project_lon_lat(self, lon: float, lat: float) -> Optional[Tuple[float, float]]:
        """
        Try the original tile-based projection first.
        If it fails (None), fall back to a simple linear mapping
        from [min_lon..max_lon] × [min_lat..max_lat] → [0..width] × [0..height].
        """
        # 1) Try existing helper – keeps consistency with tiles/sensors when it works
        pos = _latlon_to_xy_at_max_zoom(self.viewer, lat, lon)
        if pos:
            xb, yb = pos
            sx = (xb - self.viewer._x_min_base) * TILE_SIZE
            sy = (yb - self.viewer._y_min_base) * TILE_SIZE
            return sx, sy

        # 2) Fallback: linear mapping using known map bounds
        # Guard against division by zero
        if (
            self._map_max_lon == self._map_min_lon
            or self._map_max_lat == self._map_min_lat
        ):
            return None

        # Normalize lon/lat into [0,1]
        x_norm = (lon - self._map_min_lon) / (self._map_max_lon - self._map_min_lon)
        y_norm = (lat - self._map_min_lat) / (self._map_max_lat - self._map_min_lat)

        # Clip just in case (should already be in [0,1])
        x_norm = max(0.0, min(1.0, x_norm))
        y_norm = max(0.0, min(1.0, y_norm))

        # Scene coords: x grows right, y grows down → flip y
        sx = x_norm * self._scene_width
        sy = (1.0 - y_norm) * self._scene_height

        return sx, sy

    # ─────────────────────────────────────────────
    def add_region(self, region: dict, start_date=None, end_date=None, selected_ids=None):
        """Add a region polygon to the orthophoto map."""
        try:
            geom_json = json.loads(region["geom"])
        except Exception as e:
            print(f"[RegionLayer] ❌ Invalid geometry for {region.get('name')}: {e}")
            return

        if not geom_json.get("coordinates"):
            print(f"[RegionLayer] ⚠️ Region {region.get('name')} missing coordinates")
            return

        coords = geom_json["coordinates"]
        gtype = geom_json.get("type")

        # Handle Polygon / MultiPolygon
        if gtype == "Polygon":
            outer_ring = coords[0]
        elif gtype == "MultiPolygon":
            # Pick the largest polygon’s outer ring
            outer_ring = max(coords, key=lambda c: len(c[0]))[0]
        else:
            print(f"[RegionLayer] ⚠️ Unsupported geom type {gtype} for {region.get('name')}")
            return

        if len(outer_ring) < 3:
            print(f"[RegionLayer] ⚠️ Region {region.get('name')} has too few points")
            return

        # ── Project region to scene coordinates
        scene_points: list[QPointF] = []
        print(f"[RegionLayer] ▶ Projecting region '{region.get('name')}'...")
        for lon, lat in outer_ring:
            proj = self._project_lon_lat(lon, lat)
            print(f"   - vertex lon={lon:.6f}, lat={lat:.6f} -> {proj}")
            if not proj:
                continue
            sx, sy = proj
            scene_points.append(QPointF(sx, sy))

        if len(scene_points) < 3:
            print(f"[RegionLayer] ⚠️ Region {region.get('name')} has too few valid projected points")
            return

        polygon = QPolygonF(scene_points)

        # ── Create graphics item
        item = QGraphicsPolygonItem(polygon)
        item.region_id = region["id"]
        item.region_name = region["name"]
        item.selected = False
        item.setZValue(900)

        pen = QPen(QColor("#111827"))
        pen.setWidthF(8)
        item.setPen(pen)

        is_selected = (selected_ids is not None) and (region["id"] in selected_ids)
        base_alpha = 100 if is_selected else 40
        item.setBrush(QColor(37, 99, 235, base_alpha))
        item.selected = bool(is_selected)

        item.setAcceptHoverEvents(True)
        item.setFlag(QGraphicsPolygonItem.GraphicsItemFlag.ItemIsSelectable, True)

        item.mousePressEvent = lambda e, it=item: self._toggle_selection(it)
        self.scene.addItem(item)
        self.regions.append(item)

        print(
            f"[RegionLayer] ✅ Added region '{item.region_name}' "
            f"(ID {item.region_id}) with {len(scene_points)} vertices"
        )

    # ─────────────────────────────────────────────
    def _toggle_selection(self, item: QGraphicsPolygonItem):
        """Toggle fill color when selected and trigger callback."""
        item.selected = not item.selected
        item.setBrush(QColor(37, 99, 235, 100 if item.selected else 40))

        if self.on_select:
            self.on_select(item.region_id, item.selected)

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
