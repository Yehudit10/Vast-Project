from __future__ import annotations
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal

class SessionManager(QObject):
    """
    Simple session holder (Singleton-like).
    Stores current user and role; emits 'sessionChanged' when updated.
    """
    sessionChanged = pyqtSignal()

    _instance: "SessionManager | None" = None

    def __new__(cls) -> "SessionManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance # type: ignore[return-value]

    def __init__(self) -> None:
        super().__init__()
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._user: Optional[str] = None
            self._role: Optional[str] = None

    @property
    def user(self) -> Optional[str]:
        return self._user

    @property
    def role(self) -> Optional[str]:
        return self._role

    def login(self, user: str, role: str) -> None:
        self._user = user
        self._role = role
        self.sessionChanged.emit()

    def logout(self) -> None:
        self._user = None
        self._role = None
        self.sessionChanged.emit()