from typing import Optional
from PyQt5.QtWidgets import QWidget
from .viewer import OrthophotoViewer

def create_orthophoto_viewer(tiles_path: str,
                             forced_scheme: Optional[str] = None,
                             parent: Optional[QWidget] = None) -> OrthophotoViewer:
    """
    Integration-friendly factory: returns a ready OrthophotoViewer widget.
    No QApplication is created here.
    """
    v = OrthophotoViewer(tiles_path=tiles_path, forced_scheme=forced_scheme, parent=parent)
    return v
