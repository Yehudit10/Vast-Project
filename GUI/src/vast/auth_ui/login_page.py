from __future__ import annotations
from typing import Callable
from PyQt6.QtCore import Qt, QSettings, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QFormLayout, QStackedWidget, QCheckBox, QSpacerItem, QSizePolicy
)
from .service import AuthService
from .widgets import ErrorBanner


class LoginPage(QWidget):
    logged_in = pyqtSignal(str, str)  # username, password (or token)
    def __init__(self, on_login: Callable, on_go_signup: Callable, auth: AuthService, parent=None) -> None:
        super().__init__(parent)
        self.auth = auth
        self.on_login = on_login
        self.on_go_signup = on_go_signup
        self.settings = QSettings("AgriSense", "FarmMonitor")
        self._build()

    def _build(self) -> None:
        title = QLabel("Welcome back 👋")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 600;")

        self.banner = ErrorBanner()

        self.email = QLineEdit()
        self.email.setPlaceholderText("you@example.com")
        self.email.setClearButtonEnabled(True)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Your password")
        self.password.setClearButtonEnabled(True)

        toggle_action = QAction("Show")
        toggle_action.setCheckable(True)
        toggle_action.toggled.connect(self._toggle_password)
        self.password.addAction(toggle_action, QLineEdit.ActionPosition.TrailingPosition)

        self.remember = QCheckBox("Remember me")

        form = QFormLayout()
        form.addRow("Email", self.email)
        form.addRow("Password", self.password)
        form.addRow("", self.remember)

        login_btn = QPushButton("Sign in")
        login_btn.clicked.connect(self._do_login)
        login_btn.setDefault(True)

        go_signup = QPushButton("Create an account")
        go_signup.setFlat(True)
        go_signup.clicked.connect(lambda: self.on_go_signup())

        main = QVBoxLayout(self)
        main.addWidget(title)
        main.addWidget(self.banner)
        main.addLayout(form)
        main.addWidget(login_btn)
        main.addItem(QSpacerItem(0, 12, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        main.addWidget(go_signup, alignment=Qt.AlignmentFlag.AlignCenter)
        main.addStretch(1)

        last_email = self.settings.value("last_email", "")
        if last_email:
            self.email.setText(last_email)
            self.remember.setChecked(True)

    def _toggle_password(self, checked: bool) -> None:
        self.password.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    def _do_login(self) -> None:
        try:
            email = self.email.text().strip()
            password = self.password.text()
            user = self.auth.login(email, password)
            if self.remember.isChecked():
                self.settings.setValue("last_email", email)
            else:
                self.settings.remove("last_email")
            self.on_login(user)
        except Exception as e:
            self.banner.show_message(str(e))
