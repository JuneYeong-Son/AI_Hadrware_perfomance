"""Password hashing, JWT tokens, shareable codes, and measurement signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from .config import settings

# Excludes easily confused characters (0/O, 1/I/L) so codes are readable aloud.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _bcrypt_input(password: str) -> bytes:
    # bcrypt silently truncates at 72 bytes; pre-hashing removes that ceiling
    # and any embedded-NUL issues while keeping the input a fixed 44 bytes.
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_input(password), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bcrypt_input(password), password_hash.encode("ascii"))
    except ValueError:
        return False


def create_access_token(user_id: int, token_version: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])


def random_code(prefix: str = "", groups: int = 2, group_len: int = 4) -> str:
    body = "-".join(
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(group_len))
        for _ in range(groups)
    )
    return f"{prefix}{body}" if prefix else body


def new_device_secret() -> str:
    return secrets.token_hex(32)


def canonical_hash(core: dict[str, Any]) -> str:
    """Stable sha256 over the core measurement fields (key order independent)."""
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def sign(secret_hex: str, message: str) -> str:
    return hmac.new(
        bytes.fromhex(secret_hex), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()
