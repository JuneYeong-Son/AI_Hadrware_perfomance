"""Signup / login / logout / current-user endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import security
from ..database import get_db
from ..deps import get_current_user
from ..models import User
from ..schemas import LoginRequest, SignupRequest, Token, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=Token, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> Token:
    exists = db.scalar(select(User).where(User.email == body.email.lower()))
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        )
    user = User(
        email=body.email.lower(),
        display_name=body.display_name,
        password_hash=security.hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=security.create_access_token(user.id, user.token_version))


@router.post("/login", response_model=Token)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not security.verify_password(body.password, user.password_hash):
        # Same message for both cases so we don't leak which emails exist.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return Token(access_token=security.create_access_token(user.id, user.token_version))


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict[str, str]:
    # Bumping token_version invalidates every token issued to this user.
    user.token_version += 1
    db.commit()
    return {"status": "logged_out"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
