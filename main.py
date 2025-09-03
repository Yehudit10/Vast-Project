from __future__ import annotations
import sys, traceback
from PyQt6.QtWidgets import QApplication
from main_window import MainWindow
from dashboard_api import DashboardApi
# from session_manager import SessionManager  # temporarily disabled

def excepthook(exctype, value, tb):
    print("\n=== Uncaught exception ===")
    traceback.print_exception(exctype, value, tb)
    print("==========================\n")
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = excepthook

def main() -> int:
    print("[main] starting QApplication")
    app = QApplication(sys.argv)

    # print("[main] logging in demo session")
    # SessionManager().login(user="demo@vast.local", role="Operator")  # skip for now

    print("[main] creating MainWindow")
    api = DashboardApi()
    win = MainWindow(api)
    win.show()
    print("[main] window shown, entering event loop")
    rc = app.exec()
    print(f"[main] event loop exited with code {rc}")
    return rc

if __name__ == "__main__":
    sys.exit(main())
