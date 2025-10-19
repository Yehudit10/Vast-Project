from __future__ import annotations
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from .ui.viewer import OrthophotoViewer
from .ag_io.sensors_api import get_sensors

def _patch_qt_plugin_paths():
    pass

def main():
    # _patch_qt_plugin_paths()

    app = QApplication(sys.argv)

    tiles_folder = r".\orthophoto_canvas\data\tiles"
    viewer = OrthophotoViewer(tiles_folder)

    # Fetch sensors from the API and display them
    try:
        sensors = get_sensors()
        viewer.set_sensors(sensors)
    except Exception as e:
        print(f"[SENSORS] failed to fetch: {e}")

    viewer.setWindowTitle("Orthophoto Viewer")
    viewer.resize(1200, 900)
    viewer.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
