# import os
# for k in list(os.environ):
#     if k.startswith(("QTWEBENGINE", "QT_QPA", "QT_PLUGIN", "QT_")):
#         os.environ.pop(k, None)
from __future__ import annotations
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from .ui.viewer import OrthophotoViewer
from .ag_io.sensors_api import get_sensors
# import os, PyQt6
# from PyQt6 import QtCore 

def _patch_qt_plugin_paths():
    pass
    # qt_pkg_dir = os.path.dirname(PyQt6.__file__)
    # qt_plugins = os.path.join(qt_pkg_dir, "Qt5", "plugins")
    # qt_bin     = os.path.join(qt_pkg_dir, "Qt5", "bin")

    # os.environ["PATH"] = qt_bin + os.pathsep + os.environ.get("PATH", "")

    # # clear/set plugin paths to avoid falling back on OSGeo4W
    # os.environ["QT_PLUGIN_PATH"] = qt_plugins
    # os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(qt_plugins, "platforms")

    # # explicitly set the library paths in case the env vars are not picked up
    # QtCore.QCoreApplication.setLibraryPaths([qt_plugins])

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
