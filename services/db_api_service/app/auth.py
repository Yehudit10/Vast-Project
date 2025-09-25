# app/auth.py
from __future__ import annotations

import os
import uuid
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from pydantic import BaseModel

from .db import session_scope
from .models import User, ServiceAccount, RefreshToken

ENV = os.getenv("ENV", "dev")
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-please-very-secret")
JWT_ALGO = os.getenv("JWT_ALGO", "HS256")
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "15"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS", "14"))

DEV_ADMIN_USER = os.getenv("DEV_ADMIN_USER", "admin")
DEV_ADMIN_PASS = os.getenv("DEV_ADMIN_PASS", "admin123")
DEV_SA_NAME = os.getenv("DEV_SA_NAME", "db-api")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)
router = APIRouter(prefix="/auth", tags=["auth"])

def get_db():
    with session_scope() as s:
        yield s

# ---------- Hashing / Verify ----------
def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)

def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)

def hash_sa_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

# ---------- JWT helpers ----------
def _encode_token(payload: dict) -> str:
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

def _decode_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])

def create_access_token(sub: str, subject_type: str = "user") -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=ACCESS_TTL_MIN)
    payload = {"sub": sub, "sub_type": subject_type, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return _encode_token(payload)

def create_refresh_token(user_id: int) -> tuple[str, datetime]:
    token = str(uuid.uuid4())
    expires = datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS)
    return token, expires

# ---------- Guard: require_auth ----------
def require_auth(
    request: Request,
    db: Session = Depends(get_db),
    bearer_token: Optional[str] = Depends(oauth2_scheme),
) -> Tuple[str, object]:
    raw_sa = request.headers.get("X-Service-Token")
    if raw_sa:
        h = hash_sa_token(raw_sa)
        sa = db.query(ServiceAccount).filter(ServiceAccount.token_hash == h).first()
        if not sa:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid service token")
        return ("service", sa)

    if not bearer_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing token")

    try:
        payload = _decode_token(bearer_token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")

    if payload.get("sub_type") != "user":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid subject type")

    user_id = int(payload["sub"]) if str(payload.get("sub", "")).isdigit() else None
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid subject")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")

    return ("user", user)

# ---------- Endpoints ----------
@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form.username).first()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad credentials")
    access = create_access_token(str(user.id), "user")
    refresh_token, expires = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token=refresh_token, expires_at=expires))
    return {"access_token": access, "token_type": "bearer", "refresh_token": refresh_token}

class RefreshIn(BaseModel):
    refresh_token: str

@router.post("/refresh")
def refresh_token(body: RefreshIn, db: Session = Depends(get_db)):
    rt = db.query(RefreshToken).filter(RefreshToken.token == body.refresh_token).first()
    if not rt:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    user = rt.user
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="inactive user")

    if rt.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh token expired")

    try:
        _decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid refresh token")

    access = create_access_token(str(user.id), "user")
    db.delete(rt)
    new_refresh, new_expires = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token=new_refresh, expires_at=new_expires))
    db.commit()

    return {"access_token": access, "refresh_token": new_refresh, "token_type": "bearer"}

class DevBootstrapIn(BaseModel):
    service_name: str | None = None
    rotate_if_exists: bool = False

@router.post("/_dev_bootstrap", status_code=status.HTTP_201_CREATED)
def dev_bootstrap(body: DevBootstrapIn | None = None, db: Session = Depends(get_db)):
    if ENV != "dev":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="for dev only")

    service_name = (body.service_name.strip() if body and body.service_name else DEV_SA_NAME).strip()
    rotate = bool(body.rotate_if_exists) if body else False
    if not service_name:
        raise HTTPException(status_code=400, detail="service_name required")

    user = db.query(User).filter(User.username == DEV_ADMIN_USER).first()
    created_user = False
    if not user:
        user = User(username=DEV_ADMIN_USER, password_hash=hash_password(DEV_ADMIN_PASS))
        db.add(user)
        db.flush()
        created_user = True

    sa = db.query(ServiceAccount).filter(ServiceAccount.name == service_name).first()
    raw_sa_token: Optional[str] = None

    if not sa:
        raw_sa_token = str(uuid.uuid4())
        sa = ServiceAccount(name=service_name, token_hash=hash_sa_token(raw_sa_token))
        db.add(sa)
    else:
        if rotate:
            raw_sa_token = str(uuid.uuid4())
            sa.token_hash = hash_sa_token(raw_sa_token)

    access = create_access_token(str(user.id), "user")
    refresh_token, expires = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token=refresh_token, expires_at=expires))

    return {
        "created_user": created_user,
        "service_account": {
            "name": sa.name,
            "raw_token": raw_sa_token or None,
            "token": (raw_sa_token or "*** (already exists)"),
        },
        "tokens": {
            "access_token": access,
            "refresh_token": refresh_token,
            "token_type": "bearer",
        },
    }
