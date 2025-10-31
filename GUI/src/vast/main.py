from __future__ import annotations

import os
import sys
import traceback
import inspect
from pathlib import Path

import PyQt6

for k in list(os.environ):
    if k.startswith(("QTWEBENGINE", "QT_QPA", "QT_PLUGIN", "QT_")):
        os.environ.pop(k, None)

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
    def __init__(self, parent=None):
        super().__init__(parent)
        self.auth = AuthService()
        self.login_page = None
        self.signup_page = None
        self._build_pages()

    def _build_pages(self):
        def go_signup():
            self.setCurrentWidget(self.signup_page)

        def go_login():
            self.setCurrentWidget(self.login_page)

        def on_signed_up():
            self.setCurrentWidget(self.login_page)

        def on_login_success(user):
            if hasattr(self, "on_login_success") and callable(self.on_login_success):
                self.on_login_success(user)

        self.login_page = LoginPage(on_login=on_login_success,
                                    on_go_signup=go_signup,
                                    auth=self.auth)
        self.signup_page = SignupPage(on_signed_up=on_signed_up,
                                      on_go_login=go_login,
                                      auth=self.auth)

        self.addWidget(self.login_page)
        self.addWidget(self.signup_page)
        self.setCurrentWidget(self.login_page)

    def reset(self):
        self.setCurrentWidget(self.login_page)


def main() -> int:
    print("[main] starting QApplication")


    import os
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --disable-software-rasterizer"
    os.environ["QT_QUICK_BACKEND"] = "software"

    app = QApplication(sys.argv)


    from PyQt6 import QtWidgets
    
    from PyQt6.QtWidgets import QStyleFactory
    print("Available QStyles:", QStyleFactory.keys())
    # app = QApplication([])
    
    print("Current style:", app.style().objectName())
    app.setStyle("gtk3") 
        # shell = AuthShell()
    # shell.setWindowTitle("Sign in")
    # shell.show()

    # def open_main(user):
    api = DashboardApi()
    win = MainWindow(api)
    # win.logoutRequested.connect(lambda: on_logout(win))
    win.show()
    # shell.hide()

    # def on_logout(win):
    #     win.close()
    #     shell.reset()
    #     shell.show()

    # shell.on_login_success = open_main

    print("[main] window shown, entering event loop")
    rc = app.exec()
    print(f"[main] event loop exited with code {rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
