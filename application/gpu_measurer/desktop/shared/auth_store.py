"""Local persistence of the logged-in session (token + user profile).

Stored as a small JSON file in the per-user config directory so the app can
auto-login on the next launch. This is a convenience cache, not a secret store —
logout deletes it, and the token is server-invalidated on logout regardless.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import QStandardPaths


def _session_file() -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    directory = Path(base) / "GpuPerf" if base else Path.home() / ".gpu_perf"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "session.json"


def save_session(token: str, user: dict[str, Any]) -> None:
    try:
        _session_file().write_text(
            json.dumps({"token": token, "user": user}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        # A cache write failure must never crash the app; auto-login just won't
        # persist this time.
        pass


def load_session() -> dict[str, Any] | None:
    try:
        path = _session_file()
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and data.get("token") else None
    except (OSError, ValueError):
        return None


def clear_session() -> None:
    try:
        _session_file().unlink(missing_ok=True)
    except OSError:
        pass
