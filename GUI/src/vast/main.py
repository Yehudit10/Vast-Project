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


# def main() -> int:
#     print("[main] starting QApplication")
#     app = QApplication(sys.argv)

#     # 1) show auth shell first
#     shell = AuthShell()
#     shell.setWindowTitle("Sign in")
#     shell.show()

#     # 2) when login succeeds -> open MainWindow
#     def open_main(user):
#         api = DashboardApi()  # pass user if needed
#         win = MainWindow(api)

#         # connect logout back to login
#         win.logoutRequested.connect(lambda: on_logout(win))

#         win.show()
#         shell.hide()

  
#     def on_logout(win):
#         win.close()
#         shell.reset()
#         shell.show()

#     # wire callback
#     shell.on_login_success = open_main

#     print("[main] window shown, entering event loop")
#     rc = app.exec()
#     print(f"[main] event loop exited with code {rc}")
#     return rc


# if __name__ == "__main__":
#     sys.exit(main())

def main() -> int:
    print("[main] starting QApplication")
    app = QApplication(sys.argv)
    # 1) create the auth shell but do NOT show it
    shell = AuthShell()
    shell.setWindowTitle("Sign in")
    # shell.show()   # disabled to skip the login window
    # 2) when login succeeds -> open MainWindow
    def open_main(user):
        api = DashboardApi()  # create API instance (user not required)
        win = MainWindow(api)
        # connect logout back to login
        win.logoutRequested.connect(lambda: on_logout(win))
        win.show()
        shell.hide()
    def on_logout(win):
        win.close()
        shell.reset()
        shell.show()
    # wire callback
    shell.on_login_success = open_main
    # open the main window directly (skip login)
    open_main(None)
    print("[main] window shown, entering event loop")
    rc = app.exec()
    print(f"[main] event loop exited with code {rc}")
    return rc
if __name__ == "__main__":
    sys.exit(main())