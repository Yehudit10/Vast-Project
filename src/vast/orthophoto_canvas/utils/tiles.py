# utils/tiles.py
from __future__ import annotations
from pathlib import Path
import os
from typing import Dict, List, Tuple, Optional

_EXTS = (".png", ".jpg", ".jpeg")


class TileStore:
    """
    Small helper around a tiles root folder laid out as {root}/{z}/{x}/{y}.ext
    (XYZ or TMS).
    Scans available zoom levels and x/y ranges, detects XYZ vs TMS, and
    provides helpers to locate tile files.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        if not self.root.exists() or not self.root.is_dir():
            raise FileNotFoundError(f"Tiles root does not exist or is not a directory: {self.root}")

        self.existing_zooms: List[int] = self._scan_existing_zooms()
        if not self.existing_zooms:
            raise FileNotFoundError(f"No zoom folders found under: {self.root}")

        self.min_zoom: int = min(self.existing_zooms)
        self.max_zoom: int = max(self.existing_zooms)

        # map[z] = (x_min, x_max, y_min, y_max)
        self.z_ranges: Dict[int, Tuple[int, int, int, int]] = self._scan_index_ranges()

        # detect XYZ/TMS
        self.is_tms: bool = self._detect_scheme()

    # ---------- scans ----------

    def _scan_existing_zooms(self) -> List[int]:
        """Return sorted zooms (dir names that are all digits) under root."""
        zs: List[int] = []
        try:
            with os.scandir(self.root) as it:
                for e in it:
                    if e.is_dir() and e.name.isdigit():
                        zs.append(int(e.name))
        except OSError as ex:
            raise OSError(f"Failed to scan tiles root: {self.root}") from ex
        zs.sort()
        return zs

    def _scan_index_ranges(self) -> Dict[int, Tuple[int, int, int, int]]:
        """
        For each zoom z, compute:
          x_min..x_max from subfolders, and y_min..y_max from filenames inside those x folders.
        """
        ranges: Dict[int, Tuple[int, int, int, int]] = {}
        for z in self.existing_zooms:
            zdir = self.root / str(z)
            if not zdir.is_dir():
                continue

            xs: List[int] = []
            try:
                with os.scandir(zdir) as it:
                    for e in it:
                        if e.is_dir() and e.name.isdigit():
                            xs.append(int(e.name))
            except OSError:
                continue

            if not xs:
                continue

            x_min, x_max = min(xs), max(xs)

            # collect all y values (numeric stems with allowed image extensions)
            ys: List[int] = []
            for x in xs:
                xdir = zdir / str(x)
                try:
                    with os.scandir(xdir) as it:
                        for e in it:
                            if not e.is_file():
                                continue
                            stem, ext = os.path.splitext(e.name)
                            if stem.isdigit() and ext.lower() in _EXTS:
                                ys.append(int(stem))
                except OSError:
                    continue

            if ys:
                y_min, y_max = min(ys), max(ys)
            else:
                # no y found – degrade gracefully (still allow positioning by x)
                y_min = y_max = 0

            ranges[z] = (x_min, x_max, y_min, y_max)

        if not ranges:
            raise FileNotFoundError(
                f"No x/y tiles found under zoom folders in: {self.root}"
            )
        return ranges

    # ---------- scheme detection (XYZ vs TMS) ----------

    def _detect_scheme(self) -> bool:
        """
        Returns True if TMS (Y is flipped), otherwise False (XYZ).
        Heuristic: pick high zoom z, choose an x with files, grab a y from it,
        probe both XYZ and TMS paths — prefer XYZ if both exist.
        """
        z = self.max_zoom
        zdir = self.root / str(z)

        xs = self.list_existing_x(z)
        # try a few centered xs
        xs_sorted = sorted(xs, key=lambda xv: abs(xv - ((min(xs) + max(xs)) // 2))) if xs else xs

        for x in xs_sorted[:10]:  # probe a few
            ys = self.list_existing_y(z, x)
            if not ys:
                continue
            # pick a "middle" y to avoid edge bias
            y = ys[len(ys) // 2]

            if self._tile_path_xyz(z, x, y) is not None:
                # XYZ found — prefer it
                return False

            # Check TMS flip
            y_max = (1 << z) - 1
            y_tms = y_max - y
            if self._tile_path_tms(z, x, y_tms) is not None:
                return True

        # default to XYZ if unsure
        return False

    # ---------- public helpers ----------

    def list_existing_x(self, z: int) -> List[int]:
        zdir = self.root / str(z)
        if not zdir.is_dir():
            return []
        xs: List[int] = []
        try:
            with os.scandir(zdir) as it:
                for e in it:
                    if e.is_dir() and e.name.isdigit():
                        xs.append(int(e.name))
        except OSError:
            return []
        xs.sort()
        return xs

    def list_existing_y(self, z: int, x: int) -> List[int]:
        xdir = self.root / str(z) / str(x)
        if not xdir.is_dir():
            return []
        ys: List[int] = []
        try:
            with os.scandir(xdir) as it:
                for e in it:
                    if not e.is_file():
                        continue
                    stem, ext = os.path.splitext(e.name)
                    if stem.isdigit() and ext.lower() in _EXTS:
                        ys.append(int(stem))
        except OSError:
            return []
        ys.sort()
        return ys

    def tile_path(self, z: int, x: int, y: int) -> Optional[str]:
        """Return absolute file path (str) to an existing tile, or None."""
        if self.is_tms:
            return self._tile_path_tms(z, x, y)
        return self._tile_path_xyz(z, x, y)

    # ---------- path building ----------

    def _tile_path_xyz(self, z: int, x: int, y: int) -> Optional[str]:
        base = self.root / str(z) / str(x)
        for ext in _EXTS:
            p = base / f"{y}{ext}"
            if p.exists():
                return str(p)
        return None

    def _tile_path_tms(self, z: int, x: int, y: int) -> Optional[str]:
        # flip Y: y_tms = (2^z - 1) - y
        y_max = (1 << z) - 1
        y_tms = y_max - y
        base = self.root / str(z) / str(x)
        for ext in _EXTS:
            p = base / f"{y_tms}{ext}"
            if p.exists():
                return str(p)
        return None
