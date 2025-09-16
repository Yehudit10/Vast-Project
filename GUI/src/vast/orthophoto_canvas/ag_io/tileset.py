# orthophoto_canvas/ag_io/tileset.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class TileStore:
    """
    Minimal tileset adapter for OrthophotoViewer.

    Expects folder layout:
        <root>/<z>/<x>/<y>.png|jpg|jpeg

    Builds:
      - existing_zooms: list[int]
      - min_zoom, max_zoom: ints
      - z_ranges[z]: (x_min, x_max, y_min, y_max)
      - is_tms: bool  (true if scheme == 'TMS')
    And provides:
      - tile_path(z, x, y) -> str | None
    """

    def __init__(self, root: Path | str, scheme: Optional[str] = None) -> None:
        self.root = str(root)
        self.scheme = (scheme or self._detect_scheme()).upper()
        if self.scheme not in ("XYZ", "TMS"):
            self.scheme = "XYZ"

        self.existing_zooms: List[int] = []
        self.z_ranges: Dict[int, Tuple[int, int, int, int]] = {}

        # Scan the directory tree to discover available tiles and ranges
        self._scan_tree()

        if self.existing_zooms:
            self.min_zoom = min(self.existing_zooms)
            self.max_zoom = max(self.existing_zooms)
        else:
            # fallbacks to allow the viewer to start even on empty sets
            self.min_zoom = 0
            self.max_zoom = 0

    # ---- helpers ----

    def _detect_scheme(self) -> str:
        """
        If a text file '<root>/scheme.txt' exists, read first token (XYZ/TMS).
        Otherwise default to 'XYZ'.
        """
        cand = os.path.join(self.root, "scheme.txt")
        try:
            with open(cand, "r", encoding="utf-8") as f:
                token = f.read().strip().upper()
                if token in ("XYZ", "TMS"):
                    return token
        except Exception:
            pass
        return "XYZ"

    def _scan_tree(self) -> None:
        """
        Populate existing_zooms and z_ranges by scanning the filesystem.
        """
        if not os.path.isdir(self.root):
            return

        for z_name in os.listdir(self.root):
            if not z_name.isdigit():
                continue
            z = int(z_name)
            z_dir = os.path.join(self.root, z_name)
            if not os.path.isdir(z_dir):
                continue

            # collect x folders
            xs: List[int] = [int(d) for d in os.listdir(z_dir)
                             if d.isdigit() and os.path.isdir(os.path.join(z_dir, d))]
            if not xs:
                continue

            x_min, x_max = min(xs), max(xs)

            # collect y files
            ys: List[int] = []
            for x in xs:
                x_dir = os.path.join(z_dir, str(x))
                if not os.path.isdir(x_dir):
                    continue
                for fname in os.listdir(x_dir):
                    stem, ext = os.path.splitext(fname)
                    if stem.isdigit() and ext.lower() in (".png", ".jpg", ".jpeg"):
                        ys.append(int(stem))

            if not ys:
                continue

            y_min, y_max = min(ys), max(ys)
            self.existing_zooms.append(z)
            self.z_ranges[z] = (x_min, x_max, y_min, y_max)

        # keep zooms sorted for nicer behavior
        self.existing_zooms.sort()

    # ---- properties expected by the viewer ----

    @property
    def is_tms(self) -> bool:
        return self.scheme == "TMS"

    # ---- tile lookup ----

    def tile_path(self, z: int, x: int, y: int) -> Optional[str]:
        """
        Return existing file path for (z, x, y), respecting XYZ vs TMS.
        """
        base = os.path.join(self.root, str(z), str(x))

        def first_existing(candidates: List[str]) -> Optional[str]:
            for p in candidates:
                if os.path.exists(p):
                    return p
            return None

        if self.scheme == "TMS":
            # flip y
            y = ((1 << z) - 1) - y

        candidates = [
            os.path.join(base, f"{y}.png"),
            os.path.join(base, f"{y}.jpg"),
            os.path.join(base, f"{y}.jpeg"),
        ]
        return first_existing(candidates)


__all__ = ["TileStore"]
