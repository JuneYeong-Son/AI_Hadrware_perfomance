"""Runtime settings, read from the environment with safe local defaults."""

from __future__ import annotations

import os


class Settings:
    def __init__(self) -> None:
        # CHANGE THIS IN PRODUCTION (>=32 bytes). Any token signed with the old
        # key becomes invalid when this changes — the desired rotation behavior.
        self.secret_key = os.environ.get(
            "GPUPERF_SECRET_KEY", "dev-insecure-change-me-0123456789abcdef"
        )
        self.database_url = os.environ.get(
            "GPUPERF_DATABASE_URL", "sqlite:///./gpuperf.db"
        )
        self.algorithm = "HS256"
        # Access tokens are long-lived because the desktop app stores one and
        # "logout" is enforced server-side via the user's token_version.
        self.access_token_ttl_minutes = int(
            os.environ.get("GPUPERF_TOKEN_TTL_MIN", str(60 * 24 * 30))  # 30 days
        )
        # Comma-separated list, or "*" for any origin (dev default).
        self.cors_origins = os.environ.get("GPUPERF_CORS_ORIGINS", "*")


settings = Settings()
