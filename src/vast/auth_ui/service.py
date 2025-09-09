from __future__ import annotations
import os
import re
from typing import Dict
from argon2 import PasswordHasher, exceptions as argon2_exc
from .models import User

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

# Tune to your hardware so hashing ~100–300 ms
ph = PasswordHasher(time_cost=3, memory_cost=102_400, parallelism=2)  # ~100 MiB

# Optional pepper (defense-in-depth). Store outside DB (env var / keychain)
PEPPER = os.getenv("FARMMONITOR_PWD_PEPPER", "")

def _pepper(pw: str) -> str:
    return pw + PEPPER

class AuthService:
    """Demo auth service using Argon2id.
    TODO: Replace with real API calls and persistent storage.
    """
    def __init__(self) -> None:
        self._users: Dict[str, User] = {}

    def register(self, email: str, password: str, full_name: str) -> None:
        email_lc = email.strip().lower()
        if not EMAIL_RE.match(email_lc):
            raise ValueError("Please enter a valid email address.")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters.")
        if email_lc in self._users:
            raise ValueError("This email is already registered.")
        encoded = ph.hash(_pepper(password))
        self._users[email_lc] = User(email=email_lc, full_name=full_name.strip(), pw_encoded=encoded)

    def login(self, email: str, password: str) -> User:
        email_lc = email.strip().lower()
        u = self._users.get(email_lc)
        if not u:
            raise ValueError("No account found for this email.")
        try:
            ph.verify(u.pw_encoded, _pepper(password))
        except argon2_exc.VerifyMismatchError:
            raise ValueError("Incorrect password.")
        if ph.check_needs_rehash(u.pw_encoded):
            u.pw_encoded = ph.hash(_pepper(password))
        return u
