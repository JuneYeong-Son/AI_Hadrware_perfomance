"""Shared FastAPI dependencies (current-user resolution)."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import security
from .database import get_db
from .models import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")

_CRED_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    try:
        payload = security.decode_token(token)
        user_id = int(payload["sub"])
        token_version = payload["tv"]
    except Exception:  # any decode/expiry/shape failure -> 401
        raise _CRED_EXC
    user = db.get(User, user_id)
    # token_version mismatch means the user logged out after this token issued.
    if user is None or user.token_version != token_version:
        raise _CRED_EXC
    return user
