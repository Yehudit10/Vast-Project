# orthophoto_canvas/app.py
import sys
from pathlib import Path
import argparse
from PyQt5.QtWidgets import QApplication
from .ui.viewer import OrthophotoViewer

# --- add this block at the very top of app.py (before QApplication) ---
def _ensure_qt_platform_plugins():
    """Force Qt to use the platform plugins bundled with *this* venv’s PyQt5."""
    import os, PyQt5
    from PyQt5.QtCore import QCoreApplication

    base = os.path.join(os.path.dirname(PyQt5.__file__), "Qt5", "plugins")
    plat = os.path.join(base, "platforms")

    # if there are leftover OSGeo/QGIS environment variables, clean them up
    for var in ("QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        val = os.environ.get(var, "")
        if "OSGeo4W" in val or "QGIS" in val:
            os.environ.pop(var, None)

    # force the current venv's paths
    os.environ["QT_PLUGIN_PATH"] = base
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = plat

    # also add to Qt's library paths
    QCoreApplication.addLibraryPath(base)
    QCoreApplication.addLibraryPath(plat)
# --- end block ---


def main():
    parser = argparse.ArgumentParser(description="Orthophoto viewer")
    default_tiles = Path(__file__).parent / "data" / "tiles"
    parser.add_argument("--tiles", type=Path, default=default_tiles,
                        help="Path to tiles root (XYZ/TMS)")
    args = parser.parse_args()

    _ensure_qt_platform_plugins()
    app = QApplication(sys.argv)
    viewer = OrthophotoViewer(str(args.tiles))
    viewer.setWindowTitle("Orthophoto Viewer")
    viewer.resize(1200, 900)
    viewer.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
