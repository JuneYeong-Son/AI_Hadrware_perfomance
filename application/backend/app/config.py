"""Runtime settings, read from the environment with safe local defaults."""

from __future__ import annotations

import os


def _resolve_database_url() -> str:
    # Prefer our own var; fall back to the platform-provided DATABASE_URL that
    # managed hosts (Render/Railway/Fly) inject for their Postgres add-on.
    url = (
        os.environ.get("GPUPERF_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "sqlite:///./gpuperf.db"
    )
    # Heroku/Render hand out the legacy "postgres://" scheme, which SQLAlchemy
    # 2.0 no longer accepts — normalize it to the psycopg2 dialect URL.
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    return url


class Settings:
    def __init__(self) -> None:
        # CHANGE THIS IN PRODUCTION (>=32 bytes). Any token signed with the old
        # key becomes invalid when this changes — the desired rotation behavior.
        self.secret_key = os.environ.get(
            "GPUPERF_SECRET_KEY", "dev-insecure-change-me-0123456789abcdef"
        )
        self.database_url = _resolve_database_url()
        self.algorithm = "HS256"
        # Access tokens are long-lived because the desktop app stores one and
        # "logout" is enforced server-side via the user's token_version.
        self.access_token_ttl_minutes = int(
            os.environ.get("GPUPERF_TOKEN_TTL_MIN", str(60 * 24 * 30))  # 30 days
        )
        # Comma-separated list, or "*" for any origin (dev default).
        self.cors_origins = os.environ.get("GPUPERF_CORS_ORIGINS", "*")


settings = Settings()
