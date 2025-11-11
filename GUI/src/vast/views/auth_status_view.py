
from __future__ import annotations
import os, time, jwt, requests, json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QTextEdit, QFrame,
    QMessageBox, QProgressDialog
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6 import sip


def _line():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


class AuthStatusView(QWidget):
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.access_token = None
        self.refresh_token = None
        self.expiry_ts = None
        self.all_data = []

        self.setStyleSheet("""
            QWidget {
                background-color: #101010;
                color: #e6e6e6;
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px;
            }
            QLineEdit, QComboBox {
                background-color: #1a1a1a;
                color: #e6e6e6;
                border: 1px solid #333;
                border-radius: 4px;
                padding: 6px;
            }
            QPushButton {
                background-color: #2d89ef;
                color: white;
                border: none;
                padding: 8px 14px;
                border-radius: 6px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #1e5fb4; }
            QTableWidget {
                background-color: #1a1a1a;
                gridline-color: #333;
                color: #e6e6e6;
                border: 1px solid #333;
                border-radius: 6px;
            }
            QTextEdit {
                background-color: #181818;
                border: 1px solid #333;
                color: #cccccc;
                font-family: Consolas, monospace;
                font-size: 12px;
            }
            QLabel#Title {
                font-size: 22px;
                font-weight: 700;
                color: #00bcd4;
            }
            QFrame#Card {
                background-color: #141414;
                border: 1px solid #333;
                border-radius: 10px;
                padding: 14px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("User Data Dashboard")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setObjectName("Title")
        layout.addWidget(title)
        layout.addWidget(_line())

        login_card = QFrame()
        login_card.setObjectName("Card")
        login_layout = QHBoxLayout(login_card)
        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Username")
        self.pass_edit = QLineEdit()
        self.pass_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.pass_edit.setPlaceholderText("Password")
        self.btn_login = QPushButton("Login")
        login_layout.addWidget(self.user_edit)
        login_layout.addWidget(self.pass_edit)
        login_layout.addWidget(self.btn_login)
        layout.addWidget(login_card)

        token_card = QFrame()
        token_card.setObjectName("Card")
        token_layout = QVBoxLayout(token_card)
        self.tokens_display = QTextEdit()
        self.tokens_display.setReadOnly(True)
        token_layout.addWidget(self.tokens_display)
        layout.addWidget(token_card)
        layout.addWidget(_line())

        tables_env = os.getenv("TABLES_LIST", "devices")
        self.tables = [t.strip() for t in tables_env.split(",") if t.strip()]
        select_card = QFrame()
        select_card.setObjectName("Card")
        select_layout = QHBoxLayout(select_card)
        self.table_combo = QComboBox()
        self.table_combo.addItems(self.tables)
        self.btn_load = QPushButton("Load Table Data")
        select_layout.addWidget(QLabel("Select Table:"))
        select_layout.addWidget(self.table_combo, 1)
        select_layout.addWidget(self.btn_load)
        layout.addWidget(select_card)

        search_card = QFrame()
        search_card.setObjectName("Card")
        search_layout = QHBoxLayout(search_card)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search in table...")
        search_layout.addWidget(self.search_edit)
        layout.addWidget(search_card)

        self.table_widget = QTableWidget()
        layout.addWidget(self.table_widget, 1)

        self.progress = QProgressDialog("Loading data...", None, 0, 0, self)
        self.progress.setWindowTitle("Please Wait")
        self.progress.setCancelButton(None)
        self.progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.progress.setStyleSheet("""
            QProgressDialog {
                background-color: #222;
                color: white;
                border: 2px solid #00bcd4;
                border-radius: 10px;
                font-size: 16px;
                padding: 15px;
            }
        """)
        self.progress.close()

        self.btn_login.clicked.connect(self._login)
        self.btn_load.clicked.connect(self._load_table)
        self.search_edit.textChanged.connect(self._filter_table)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_expiry_timer)
        self.timer.start(1000)

    def _login(self):
        user = self.user_edit.text().strip()
        password = self.pass_edit.text().strip()
        if not user or not password:
            QMessageBox.warning(self, "Missing Data", "Please enter both username and password.")
            return
        try:
            url = f"{self.api.base}/auth/login"
            data = {"username": user, "password": password}
            r = requests.post(url, data=data, timeout=10)
            if r.status_code == 200:
                js = r.json()
                old_token = self.access_token
                self.access_token = js.get("access_token")
                self.refresh_token = js.get("refresh_token")
                self.api.http.headers.update({"Authorization": f"Bearer {self.access_token}"})
                try:
                    payload = jwt.decode(self.access_token, options={"verify_signature": False})
                    self.expiry_ts = payload.get("exp")
                except Exception:
                    self.expiry_ts = None
                msg_prefix = "✅ Access Token updated!\n\n" if old_token and self.access_token != old_token else ""
                self.tokens_display.setPlainText(
                    f"{msg_prefix}"
                    f"Access Token:\n{self.access_token}\n\n"
                    f"Refresh Token:\n{self.refresh_token}"
                )
                QMessageBox.information(self, "Login Successful", "User authenticated successfully.")
            else:
                QMessageBox.warning(self, "Login Failed", f"Error {r.status_code}: {r.text[:200]}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to login:\n{e}")

    def _update_expiry_timer(self):
        if not self.expiry_ts or sip.isdeleted(self.tokens_display):
            return
        now = int(time.time())
        secs_left = self.expiry_ts - now
        if secs_left < 0:
            msg = "⚠ Token expired."
        else:
            mins, secs = divmod(secs_left, 60)
            msg = f"Token expires in {mins:02d}:{secs:02d}"
        self.tokens_display.setToolTip(msg)

    def _load_table(self):
        if not self.access_token:
            if not sip.isdeleted(self):
                QMessageBox.warning(self, "Not Authenticated", "Please login first.")
            return

        table_name = self.table_combo.currentText()
        url = f"{self.api.base}/api/tables/{table_name}"

        try:
            if sip.isdeleted(self):
                return
            self.progress.show()
            self.repaint()

            r = self.api.http.get(url, timeout=20)

            if r.status_code == 200:
                data = r.json()
                if not sip.isdeleted(self) and self.isVisible():
                    self._populate_table(data)
            elif not sip.isdeleted(self):
                QMessageBox.warning(self, "Request Failed", f"{r.status_code}: {r.text[:200]}")

        except Exception as e:
            if not sip.isdeleted(self):
                QMessageBox.critical(self, "Error", f"Request failed:\n{e}")
        finally:
            if hasattr(self, "progress") and not sip.isdeleted(self.progress):
                self.progress.close()


    def _populate_table(self, data):
        if sip.isdeleted(self) or sip.isdeleted(self.table_widget) or not self.isVisible():
            return

        # --- normalize input ---
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                data = [{"value": data}]
        if isinstance(data, dict) and "rows" in data:
            data = data["rows"]
        if not isinstance(data, list):
            data = [data] if data else []

        # --- handle empty ---
        if not data:
            self.table_widget.clear()
            self.table_widget.setRowCount(0)
            self.table_widget.setColumnCount(0)
            if not sip.isdeleted(self):
                QMessageBox.information(self, "Empty", "No data found for this table.")
            return

        # --- normalize rows to dicts ---
        normalized = []
        for row in data:
            if not isinstance(row, dict):
                try:
                    row = dict(row)
                except Exception:
                    row = {"value": str(row)}
            normalized.append(row)
        data = normalized

        # --- build header keys ---
        keys = sorted({k for row in data for k in row.keys()})
        if sip.isdeleted(self.table_widget):
            return

        self.table_widget.setColumnCount(len(keys))
        self.table_widget.setRowCount(len(data))
        self.table_widget.setHorizontalHeaderLabels(keys)

        # --- fill cells safely ---
        for i, row in enumerate(data):
            if sip.isdeleted(self.table_widget):
                return
            for j, key in enumerate(keys):
                val = row.get(key, "")
                try:
                    if isinstance(val, (dict, list)):
                        val = json.dumps(val, ensure_ascii=False, indent=2)
                    elif val is None:
                        val = ""
                    else:
                        val = str(val)

                    if len(val) > 1000:
                        val = val[:997] + "..."
                    item = QTableWidgetItem(val)
                    item.setToolTip(val[:3000])
                    self.table_widget.setItem(i, j, item)
                except Exception as e:
                    if not sip.isdeleted(self.table_widget):
                        self.table_widget.setItem(i, j, QTableWidgetItem(f"[error: {e}]"))

        # --- finish up ---
        self.table_widget.resizeColumnsToContents()
        self.all_data = data

    def _filter_table(self):
        if sip.isdeleted(self.table_widget):
            return
        text = self.search_edit.text().lower().strip()
        if not text:
            self._populate_table(self.all_data)
            return
        filtered = [r for r in self.all_data if any(text in str(v).lower() for v in r.values())]
        self._populate_table(filtered)
