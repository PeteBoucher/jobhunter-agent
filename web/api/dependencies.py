"""FastAPI dependency injection: DB session + authenticated user."""

import os
import sys
from typing import Generator

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# Ensure the project root is on the path so we can import src.*
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from auth import decode_jwt  # noqa: E402

from src.models import User  # noqa: E402

_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./data/jobs.db")

_kwargs: dict = {"echo": False}
if _DATABASE_URL.startswith("postgresql"):
    _kwargs.update({"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10})

_engine = create_engine(_DATABASE_URL, **_kwargs)
_SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

_bearer = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    token = creds.credentials
    try:
        payload = decode_jwt(token)
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    google_id: str = payload.get("sub", "")
    user = db.query(User).filter(User.google_id == google_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user
