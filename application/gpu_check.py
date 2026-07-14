"""Launch the GPU Check desktop app (used-GPU buyer)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gpu_measurer.desktop.app import run_buyer

if __name__ == "__main__":
    raise SystemExit(run_buyer())
