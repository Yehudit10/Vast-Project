import os
from typing import Dict, Optional, Tuple, Iterable, List
from ..orthophoto_canvas.ag_types import TileScheme

class Tileset:
    """
    Describes an on-disk tile pyramid.
    Expected layout:
      <root>/<z>/<x>/<y>.png  (XYZ)
    or  <root>/<z>/<x>/<y>.png with Y inverted (TMS).
    """

    def __init__(self, root: str, scheme: Optional[TileScheme] = None) -> None:
        self.root = root
        self.scheme: TileScheme = scheme or "XYZ"  # default; detect() can update
        self.zooms: List[int] = []
        self.ranges: Dict[int, Tuple[int, int, int, int]] = {}
        # (x_min, x_max, y_min, y_max) per z

    def scan(self) -> None:
        """
        Populate self.zooms and self.ranges by scanning the filesystem.
        TODO: optimize with os.scandir(), short-circuit, and error handling/logging.
        """
        self.zooms.clear()
        self.ranges.clear()

        try:
            for zname in os.listdir(self.root):
                zdir = os.path.join(self.root, zname)
                if not (zname.isdigit() and os.path.isdir(zdir)):
                    continue
                z = int(zname)
                xs = [int(d) for d in os.listdir(zdir)
                      if d.isdigit() and os.path.isdir(os.path.join(zdir, d))]
                if not xs:
                    continue
                x_min, x_max = min(xs), max(xs)
                ys: List[int] = []
                for x in xs:
                    xdir = os.path.join(zdir, str(x))
                    for f in os.listdir(xdir):
                        stem, ext = os.path.splitext(f)
                        if stem.isdigit() and ext.lower() in (".png", ".jpg", ".jpeg"):
                            ys.append(int(stem))
                if not ys:
                    continue
                y_min, y_max = min(ys), max(ys)
                self.zooms.append(z)
                self.ranges[z] = (x_min, x_max, y_min, y_max)
            self.zooms.sort()
        except Exception:
            # Keep silent or raise as needed
            pass

    def detect_scheme(self) -> TileScheme:
        """
        Try to detect XYZ vs TMS by probing a sample at highest z.
        TODO: implement the inversion check; for now keep current scheme.
        """
        if self.scheme not in ("XYZ", "TMS"):
            self.scheme = "XYZ"
        return self.scheme

    def tile_path(self, z: int, x: int, y: int) -> Optional[str]:
        """
        Return a file path if tile exists, respecting self.scheme.
        """
        base = os.path.join(self.root, str(z), str(x))
        candidates = (os.path.join(base, f"{y}.png"),
                      os.path.join(base, f"{y}.jpg"),
                      os.path.join(base, f"{y}.jpeg"))

        if self.scheme == "XYZ":
            for p in candidates:
                if os.path.exists(p):
                    return p
            return None
        else:  # TMS
            y_max = (1 << z) - 1
            y_tms = y_max - y
            candidates = (os.path.join(base, f"{y_tms}.png"),
                          os.path.join(base, f"{y_tms}.jpg"),
                          os.path.join(base, f"{y_tms}.jpeg"))
            for p in candidates:
                if os.path.exists(p):
                    return p
            return None
