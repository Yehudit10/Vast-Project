import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext


ALGO = os.getenv("JWT_ALGO", "HS256")
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "15"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS", "14"))
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")



def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


# JWT helpers
def create_access_token(sub: str, subject_type: str = "user") -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ACCESS_TTL_MIN)
    payload = {
        "sub": sub,
        "sub_type": subject_type,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGO)


def create_refresh_token(user_id: int) -> str:
    import uuid
    token = str(uuid.uuid4())
    exp = datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS)
    return token, exp


def decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[ALGO])