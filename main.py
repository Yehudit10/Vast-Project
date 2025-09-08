# # from __future__ import annotations
# # import os, sys
# # from pathlib import Path
# # import traceback
# # import PyQt6  # must be first

# # def _set_env_once(k: str, v: str) -> None:
# #     if not os.environ.get(k):
# #         os.environ[k] = v

# # def _short(p: Path) -> str:
# #     s = str(p.resolve())
# #     if os.name != "nt":
# #         return s
# #     try:
# #         import ctypes
# #         buf = ctypes.create_unicode_buffer(4096)
# #         r = ctypes.windll.kernel32.GetShortPathNameW(s, buf, 4096)
# #         if r:
# #             return buf.value
# #     except Exception:
# #         pass
# #     return s

# # # --- Resolve PyQt6/Qt5 paths (prefer ASCII 8.3 short paths) ---
# # qt_root = Path(PyQt6.__file__).with_name("Qt5")
# # qt_plugins = qt_root / "plugins"
# # qt_bin = qt_root / "bin"
# # qt_res = qt_root / "resources"
# # qt_trans = qt_root / "translations"

# # qt_root_s   = _short(qt_root)
# # qt_plugins_s= _short(qt_plugins)
# # qt_bin_s    = _short(qt_bin)
# # qt_res_s    = _short(qt_res)
# # qt_trans_s  = _short(qt_trans)

# # # Add DLL search dir on Windows
# # if os.name == "nt" and qt_bin.exists():
# #     try:
# #         os.add_dll_directory(qt_bin_s)
# #     except Exception:
# #         pass

# # # Core Qt plugin paths
# # _set_env_once("QT_PLUGIN_PATH", qt_plugins_s)
# # _set_env_once("QT_QPA_PLATFORM_PLUGIN_PATH", str(Path(qt_plugins_s) / "platforms"))

# # # WebEngine process
# # we_proc = Path(qt_bin_s) / "QtWebEngineProcess.exe"
# # if we_proc.exists():
# #     _set_env_once("QTWEBENGINEPROCESS_PATH", str(we_proc))

# # # Resources dir that contains icudtl*.dat and .pak files
# # res_dir = Path(qt_res_s)
# # if not any(res_dir.glob("icudtl*.dat")):
# #     cand = list(Path(qt_root_s).rglob("icudtl*.dat"))
# #     if cand:
# #         res_dir = cand[0].parent
# # _set_env_once("QTWEBENGINE_RESOURCES_PATH", str(res_dir))

# # # Locales dir
# # res_locales = Path(qt_res_s) / "qtwebengine_locales"
# # trans_locales = Path(qt_trans_s) / "qtwebengine_locales"
# # locales_dir = res_locales if res_locales.exists() else (trans_locales if trans_locales.exists() else None)
# # if locales_dir:
# #     _set_env_once("QTWEBENGINE_LOCALES_PATH", _short(locales_dir))

# # # Force ASCII data/cache inside project
# # app_root = _short(Path(__file__).resolve().parent)
# # _set_env_once("QTWEBENGINE_DATA_PATH",   str(Path(app_root) / ".qtwebengine" / "data"))
# # _set_env_once("QTWEBENGINE_CACHE_PATH",  str(Path(app_root) / ".qtwebengine" / "cache"))
# # _set_env_once("QTWEBENGINE_DEVTOOLS_PATH", str(Path(app_root) / ".qtwebengine" / "devtools"))

# # # Helpful flags on restricted machines AND force explicit resource/locale dirs
# # flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")
# # flags += f' --disable-gpu --no-sandbox --resources-dir-path="{_short(res_dir)}"'
# # if locales_dir:
# #     flags += f' --locales-dir-path="{_short(locales_dir)}"'
# # os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = flags.strip()
# # os.environ.setdefault("QTWEBENGINE_DISABLE_GPU", "1")

# # # Print debug of what we actually set
# # def _debug():
# #     print("[Qt debug]")
# #     print("  qt_root:", qt_root_s)
# #     print("  plugins:", qt_plugins_s)
# #     print("  bin:", qt_bin_s)
# #     print("  resources:", qt_res_s)
# #     print("  translations:", qt_trans_s)
# #     print("  QTWEBENGINEPROCESS_PATH:", os.environ.get("QTWEBENGINEPROCESS_PATH"))
# #     print("  QTWEBENGINE_RESOURCES_PATH:", os.environ.get("QTWEBENGINE_RESOURCES_PATH"))
# #     print("  QTWEBENGINE_LOCALES_PATH:", os.environ.get("QTWEBENGINE_LOCALES_PATH"))
# #     print("  QT_QPA_PLATFORM_PLUGIN_PATH:", os.environ.get("QT_QPA_PLATFORM_PLUGIN_PATH"))
# #     rp = Path(os.environ.get("QTWEBENGINE_RESOURCES_PATH", ""))
# #     print("  icudtl*.dat exists?:", bool(list(rp.glob("icudtl*.dat"))))
# #     print("  qtwebengine_resources*.pak exists?:", bool(list(rp.glob("qtwebengine_resources*.pak"))))

# # # Import WebEngine modules AFTER env is set
# # from PyQt6 import QtWebEngine, QtWebEngineWidgets
# # from PyQt6.QtWidgets import QApplication
# # from dashboard_api import DashboardApi
# # from main_window import MainWindow

# # def excepthook(exctype, value, tb):
# #     print("\n=== Uncaught exception ===")
# #     traceback.print_exception(exctype, value, tb)
# #     print("==========================\n")
# #     sys.__excepthook__(exctype, value, tb)

# # sys.excepthook = excepthook

# # def main() -> int:
# #     print("[main] starting QApplication")
# #     _debug()
# #     app = QApplication(sys.argv)

# #     # Initialize WebEngine explicitly (PyQt6)
# #     try:
# #         QtWebEngine.QtWebEngine.initialize()
# #     except Exception:
# #         pass

# #     print("[main] creating MainWindow")
# #     api = DashboardApi()
# #     win = MainWindow(api)
# #     win.show()
# #     print("[main] window shown, entering event loop")
# #     rc = app.exec()
# #     print(f"[main] event loop exited with code {rc}")
# #     return rc

# # if __name__ == "__main__":
# #     sys.exit(main())
# import os, inspect, PyQt6
# for k in list(os.environ):
#     if k.startswith(("QTWEBENGINE", "QT_QPA", "QT_PLUGIN", "QT_")):
#         os.environ.pop(k, None)

# # explicitly point to PyQt6 Qt6 artifacts (if someone later tries to force Qt5)
# qt6_dir = os.path.join(os.path.dirname(PyQt6.__file__), "Qt6")
# os.environ["QTWEBENGINEPROCESS_PATH"] = os.path.join(qt6_dir, "bin", "QtWebEngineProcess.exe")
# os.environ["QTWEBENGINE_RESOURCES_PATH"] = os.path.join(qt6_dir, "resources")
# os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(qt6_dir, "plugins", "platforms")

# from __future__ import annotations
# import os, sys, traceback, ctypes
# from pathlib import Path

# # ---------- Hard bootstrap for PyQt6 WebEngine on Windows ----------
# # Use 8.3 short paths to avoid non-ASCII issues in QtWebEngineProcess.
# def short_path(p: Path) -> Path:
#     # Windows only; falls back to original on failure
#     try:
#         GetShortPathNameW = ctypes.windll.kernel32.GetShortPathNameW
#         GetShortPathNameW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
#         GetShortPathNameW.restype = ctypes.c_uint
#         buf = ctypes.create_unicode_buffer(32767)
#         r = GetShortPathNameW(str(p), buf, len(buf))
#         return Path(buf.value) if r else p
#     except Exception:
#         return p

# import PyQt6  # keep before any QtWebEngine import

# qt_root = Path(PyQt6.__file__).with_name('Qt5')
# qt_root_s = short_path(qt_root)

# qt_plugins = qt_root_s / 'plugins'
# qt_platforms = qt_plugins / 'platforms'
# qt_bin = qt_root_s / 'bin'
# qt_res = qt_root_s / 'resources'
# qt_trans = qt_root_s / 'translations'

# # These two are critical:
# os.environ.setdefault('QTWEBENGINEPROCESS_PATH', str(qt_bin / 'QtWebEngineProcess.exe'))
# os.environ.setdefault('QTWEBENGINE_RESOURCES_PATH', str(qt_res))

# # Locales folder name varies; prefer resources/qtwebengine_locales
# res_locales = qt_res / 'qtwebengine_locales'
# trans_locales = qt_trans / 'qtwebengine_locales'
# if res_locales.exists():
#     os.environ.setdefault('QTWEBENGINE_LOCALES_PATH', str(res_locales))
# elif trans_locales.exists():
#     os.environ.setdefault('QTWEBENGINE_LOCALES_PATH', str(trans_locales))

# # Platform plugins path (qwindows)
# os.environ.setdefault('QT_PLUGIN_PATH', str(qt_plugins))
# os.environ.setdefault('QT_QPA_PLATFORM_PLUGIN_PATH', str(qt_platforms))

# # Make sure Qt DLLs are discoverable
# os.environ['PATH'] = str(qt_bin) + os.pathsep + os.environ.get('PATH', '')

# # In some environments the Chromium sandbox blocks file mapping; disable it.
# os.environ.setdefault('QTWEBENGINE_DISABLE_SANDBOX', '1')

# # Optional, noisy but useful first run:
# print("[Qt debug]")
# print("  qt_root:", qt_root_s)
# print("  plugins:", qt_plugins)
# print("  bin:", qt_bin)
# print("  resources:", qt_res)
# print("  translations:", qt_trans)
# print("  QTWEBENGINEPROCESS_PATH:", os.environ.get('QTWEBENGINEPROCESS_PATH'))
# print("  QTWEBENGINE_RESOURCES_PATH:", os.environ.get('QTWEBENGINE_RESOURCES_PATH'))
# print("  QTWEBENGINE_LOCALES_PATH:", os.environ.get('QTWEBENGINE_LOCALES_PATH'))
# print("  QT_QPA_PLATFORM_PLUGIN_PATH:", os.environ.get('QT_QPA_PLATFORM_PLUGIN_PATH'))
# print("  icudtl.dat exists?:", (qt_res / 'icudtl.dat').exists())

# # Import and pre-initialize WebEngine BEFORE creating your UI
# from PyQt6 import QtWebEngineWidgets
# from PyQt6.QtWebEngineWidgets import QWebEngineView

# # ---------- Your app ----------
# from PyQt6.QtWidgets import QApplication
# from main_window import MainWindow
# from dashboard_api import DashboardApi

# def excepthook(exctype, value, tb):
#     print("\n=== Uncaught exception ===")
#     traceback.print_exception(exctype, value, tb)
#     print("==========================\n")
#     sys.__excepthook__(exctype, value, tb)

# sys.excepthook = excepthook

# def main() -> int:
#     print("[main] starting QApplication")
#     app = QApplication(sys.argv)
#     print("[main] creating MainWindow")
#     api = DashboardApi()
#     win = MainWindow(api)
#     win.show()
#     print("[main] window shown, entering event loop")
#     rc = app.exec()
#     print(f"[main] event loop exited with code {rc}")
#     return rc

# if __name__ == "__main__":
#     sys.exit(main())


from __future__ import annotations

import os
import sys
import traceback
import inspect
from pathlib import Path

import PyQt6  # import first; no QtWebEngine yet

# Wipe any inherited QT_* env vars (avoid old Qt5 overrides)
for k in list(os.environ):
    if k.startswith(("QTWEBENGINE", "QT_QPA", "QT_PLUGIN", "QT_")):
        os.environ.pop(k, None)

# Debug only: show Qt6 paths (do NOT set env vars)
qt6_dir = Path(inspect.getfile(PyQt6)).with_name("Qt6")
plugins = qt6_dir / "plugins"
bin_dir = qt6_dir / "bin"
resources = qt6_dir / "resources"
print("[Qt debug]")
print("  qt_root:", qt6_dir)
print("  plugins:", plugins)
print("  bin:", bin_dir)
print("  resources:", resources)
print("  icudtl.dat exists?:", (resources / "icudtl.dat").exists())

from PyQt6.QtWebEngineWidgets import QWebEngineView  # ensures WebEngine is available
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QStackedWidget
from auth_ui.service import AuthService
from auth_ui.login_page import LoginPage
from auth_ui.signup_page import SignupPage
from dashboard_api import DashboardApi
from main_window import MainWindow


def excepthook(exctype, value, tb):
    print("\n=== Uncaught exception ===")
    traceback.print_exception(exctype, value, tb)
    print("==========================\n")
    sys.__excepthook__(exctype, value, tb)


sys.excepthook = excepthook

class AuthShell(QStackedWidget):
    """Holds Login and Signup pages and switches between them."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth = AuthService()

        # placeholders for pages (will be created below)
        self.login_page = None
        self.signup_page = None

        # build pages
        self._build_pages()

    def _build_pages(self):
        # callbacks
        def go_signup():
            self.setCurrentWidget(self.signup_page)

        def go_login():
            self.setCurrentWidget(self.login_page)

        def on_signed_up():
            # after successful signup, move back to login
            self.setCurrentWidget(self.login_page)

        def on_login_success(user):
            # bubble up to whoever created the shell
            # we’ll set this attribute from main()
            if hasattr(self, "on_login_success") and callable(self.on_login_success):
                self.on_login_success(user)

        # create pages
        self.login_page = LoginPage(on_login=on_login_success,
                                    on_go_signup=go_signup,
                                    auth=self.auth)
        self.signup_page = SignupPage(on_signed_up=on_signed_up,
                                      on_go_login=go_login,
                                      auth=self.auth)

        # add to stack
        self.addWidget(self.login_page)
        self.addWidget(self.signup_page)
        self.setCurrentWidget(self.login_page)

    def reset(self):
        """Optional: clear fields on logout if you want."""
        # for example:
        # self.login_page.email.clear()
        # self.login_page.password.clear()
        self.setCurrentWidget(self.login_page)


def main() -> int:
    print("[main] starting QApplication")
    app = QApplication(sys.argv)

    # 1) show auth shell first
    shell = AuthShell()
    shell.setWindowTitle("Sign in")
    shell.show()

    # 2) when login succeeds -> open MainWindow
    def open_main(user):
        api = DashboardApi()  # pass user if needed
        win = MainWindow(api)

        # connect logout back to login
        win.logoutRequested.connect(lambda: on_logout(win))

        # connect logout back to login
        # try:
        #     win.logoutRequested.connect(lambda: on_logout(win))
        # except Exception:
        #     # if signal not defined yet, we'll add it in main_window.py below
        #     pass
        win.show()
        shell.hide()

    # print("[main] creating MainWindow")
    # api = DashboardApi()
    # win = MainWindow(api)
    # win.show()

    def on_logout(win):
        win.close()
        shell.reset()
        shell.show()

    # wire callback
    shell.on_login_success = open_main

    print("[main] window shown, entering event loop")
    rc = app.exec()
    print(f"[main] event loop exited with code {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
