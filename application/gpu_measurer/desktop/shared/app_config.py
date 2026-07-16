"""Runtime configuration for the packaged desktop app.

The backend URL must be settable *without* recompiling, so distributors can
build the app once and point it at their hosted server by editing a JSON file
next to the executable. Resolution order (first wins):

1. ``GPUPERF_API_URL`` environment variable.
2. ``api_url`` in ``gpuperf.config.json`` beside the executable (frozen app) or
   in the current working directory (running from source).
3. ``http://127.0.0.1:8000`` (local development default).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_API_URL = "http://127.0.0.1:8000"
CONFIG_FILENAME = "gpuperf.config.json"


def _config_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    if getattr(sys, "frozen", False):
        # PyInstaller: the config sits next to the executable.
        dirs.append(Path(sys.executable).resolve().parent)
    dirs.append(Path.cwd())
    return dirs


def _from_config_file() -> str | None:
    for directory in _config_search_dirs():
        path = directory / CONFIG_FILENAME
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                url = data.get("api_url")
                if isinstance(url, str) and url.strip():
                    return url.strip().rstrip("/")
        except (OSError, ValueError):
            continue
    return None


def api_base_url() -> str:
    env = os.environ.get("GPUPERF_API_URL")
    if env and env.strip():
        return env.strip().rstrip("/")
    from_file = _from_config_file()
    if from_file:
        return from_file
    return DEFAULT_API_URL
