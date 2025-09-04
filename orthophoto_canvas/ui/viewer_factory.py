# from typing import Optional
# from PyQt5.QtWidgets import QWidget
# from .viewer import OrthophotoViewer

# def create_orthophoto_viewer(tiles_path: str,
#                              forced_scheme: Optional[str] = None,
#                              parent: Optional[QWidget] = None) -> OrthophotoViewer:
#     """
#     Integration-friendly factory: returns a ready OrthophotoViewer widget.
#     No QApplication is created here.
#     """
#     v = OrthophotoViewer(tiles_path=tiles_path, forced_scheme=forced_scheme, parent=parent)
#     return v


# orthophoto_canvas/ui/viewer_factory.py
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from PyQt5.QtWidgets import QWidget

from .viewer import OrthophotoViewer
from orthophoto_canvas.ag_io.tileset import TileStore


def create_orthophoto_viewer(
    tiles_root: Union[str, Path],
    forced_scheme: Optional[str] = None,
    parent: Optional[QWidget] = None,
) -> OrthophotoViewer:
    """
    Build and return an OrthophotoViewer widget.
    No QApplication is created here.
    """
    tiles_path = Path(tiles_root)

    # Let the viewer create the TileStore internally.
    viewer = OrthophotoViewer(tiles=tiles_path)

    # Optionally force tile scheme (TMS / XYZ).
    if forced_scheme:
        scheme = forced_scheme.lower().strip()
        if scheme in ("tms", "xyz"):
            is_tms = (scheme == "tms")
            # Try to update both the viewer and its underlying TileStore.
            try:
                viewer.is_tms = is_tms
            except Exception:
                pass
            try:
                if isinstance(viewer.ts, TileStore):
                    viewer.ts.is_tms = is_tms
            except Exception:
                pass

    if parent is not None:
        viewer.setParent(parent)

    return viewer
