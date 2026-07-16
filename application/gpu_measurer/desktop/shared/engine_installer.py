"""On-demand install of the benchmark engine (PyTorch + CUDA).

The distributed app is kept small by NOT bundling torch (several GB). The first
time a user runs a benchmark without the engine, we download torch into a
per-user directory and add it to ``sys.path``, so measuring works without a
reinstall. Subsequent launches pick it up automatically via
``ensure_engine_on_path``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable

# CUDA 12.4 wheels (matches the drivers most current NVIDIA GPUs ship with).
PYTORCH_INDEX_URL = "https://download.pytorch.org/whl/cu124"

LogFn = Callable[[str], None]


def engine_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "GpuPerf" / "engine"


def ensure_engine_on_path() -> None:
    """Make a previously installed engine importable in this process."""
    directory = engine_dir()
    if directory.is_dir():
        path = str(directory)
        if path not in sys.path:
            sys.path.insert(0, path)


def torch_importable() -> bool:
    ensure_engine_on_path()
    try:
        import torch  # noqa: F401
    except Exception:
        return False
    return True


def is_engine_available() -> bool:
    """True only when torch imports AND a CUDA GPU is usable."""
    if not torch_importable():
        return False
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def install_engine(log: LogFn | None = None) -> bool:
    """Download + install torch into the per-user engine directory.

    Runs pip in-process (the frozen app has no python.exe to shell out to) with
    a wheel-only, targeted install so nothing touches the app's own bundle.
    Returns True on success. This downloads a few GB, so call it off the UI
    thread.
    """

    def emit(message: str) -> None:
        if log:
            log(message)

    directory = engine_dir()
    directory.mkdir(parents=True, exist_ok=True)
    emit(f"설치 위치: {directory}")
    emit("엔진(PyTorch+CUDA)을 내려받는 중… 수 GB라 시간이 걸릴 수 있어요.")

    args = [
        "install",
        "--target",
        str(directory),
        "--upgrade",
        "--only-binary=:all:",
        "--index-url",
        PYTORCH_INDEX_URL,
        "torch",
    ]
    try:
        from pip._internal.cli.main import main as pip_main
    except Exception as error:  # pip not bundled / importable
        emit(f"설치 도구를 불러오지 못했어요: {error}")
        return False

    try:
        code = pip_main(args)
    except SystemExit as exit_error:  # pip may raise SystemExit
        code = int(exit_error.code) if isinstance(exit_error.code, int) else 1
    except Exception as error:  # noqa: BLE001 - surface any failure to the UI
        emit(f"설치 중 오류: {type(error).__name__}: {error}")
        return False

    if code == 0:
        ensure_engine_on_path()
        emit("설치 완료.")
        return True
    emit(f"설치 실패 (pip 코드 {code}). 인터넷 연결을 확인하고 다시 시도하세요.")
    return False
