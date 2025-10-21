from __future__ import annotations
import re
from typing import Callable
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton, QVBoxLayout,
    QFormLayout, QStackedWidget, QCheckBox
)
from .service import AuthService, EMAIL_RE
from .widgets import ErrorBanner

class SignupPage(QWidget):
    def __init__(self, on_signed_up: Callable, on_go_login: Callable, auth: AuthService, parent=None) -> None:
        super().__init__(parent)
        self.auth = auth
        self.on_signed_up = on_signed_up
        self.on_go_login = on_go_login
        self._build()

    def _build(self) -> None:
        title = QLabel("Create your account")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: 600;")

        self.banner = ErrorBanner()

        self.full_name = QLineEdit()
        self.full_name.setPlaceholderText("Full name")
        self.full_name.setClearButtonEnabled(True)

        self.email = QLineEdit()
        self.email.setPlaceholderText("you@example.com")
        self.email.setClearButtonEnabled(True)

        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("At least 8 characters")
        self.password.setClearButtonEnabled(True)

        self.confirm = QLineEdit()
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self.confirm.setPlaceholderText("Repeat password")
        self.confirm.setClearButtonEnabled(True)

        toggle_action = QAction("Show")
        toggle_action.setCheckable(True)
        toggle_action.toggled.connect(self._toggle_passwords)
        self.confirm.addAction(toggle_action, QLineEdit.ActionPosition.TrailingPosition)

        self.terms = QCheckBox("I agree to the Terms of Service and Privacy Policy")

        form = QFormLayout()
        form.addRow("Full name", self.full_name)
        form.addRow("Email", self.email)
        form.addRow("Password", self.password)
        form.addRow("Confirm", self.confirm)
        form.addRow("", self.terms)

        signup_btn = QPushButton("Sign up")
        signup_btn.clicked.connect(self._do_signup)
        signup_btn.setDefault(True)

        go_login = QPushButton("Already have an account? Sign in")
        go_login.setFlat(True)
        go_login.clicked.connect(lambda: self.on_go_login())

        main = QVBoxLayout(self)
        main.addWidget(title)
        main.addWidget(self.banner)
        main.addLayout(form)
        main.addWidget(signup_btn)
        main.addWidget(go_login, alignment=Qt.AlignmentFlag.AlignCenter)
        main.addStretch(1)

    def _toggle_passwords(self, checked: bool) -> None:
        mode = QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        self.password.setEchoMode(mode)
        self.confirm.setEchoMode(mode)

    def _do_signup(self) -> None:
        try:
            full_name = self.full_name.text().strip()
            email = self.email.text().strip()
            password = self.password.text()
            confirm = self.confirm.text()

            if not full_name:
                raise ValueError("Please enter your full name.")
            if not EMAIL_RE.match(email):
                raise ValueError("Please enter a valid email address.")
            if len(password) < 8:
                raise ValueError("Password must be at least 8 characters.")
            if password != confirm:
                raise ValueError("Passwords do not match.")
            if not self.terms.isChecked():
                raise ValueError("You must accept the Terms to continue.")

            self.auth.register(email=email, password=password, full_name=full_name)
            from PyQt6.QtWidgets import QMessageBox  # local import to avoid circulars in stubs
            QMessageBox.information(self, "Account created", "Your account has been created. Please sign in.")
            self.on_go_login()
            self.on_signed_up()
        except Exception as e:
            self.banner.show_message(str(e))
