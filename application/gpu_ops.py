"""Launch the GPU Ops desktop app (AI server operator)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpu_measurer.desktop.app import run_operator

if __name__ == "__main__":
    raise SystemExit(run_operator())
