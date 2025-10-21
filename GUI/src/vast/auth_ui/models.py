from __future__ import annotations
from dataclasses import dataclass

@dataclass
class User:
    email: str
    full_name: str
    pw_encoded: str  # Argon2 encoded hash string
