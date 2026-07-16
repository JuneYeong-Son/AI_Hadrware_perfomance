#!/usr/bin/env bash
# Build the macOS desktop apps (GPU Check + GPU Ops) as .app bundles under dist/.
# Run on a Mac with Python 3.11+.
#
#   bash packaging/build_macos.sh            # standard build
#
# Note: macOS has no CUDA, so the TFLOPS benchmark does not run there — the app
# is useful for GPU info, sensors, account login, and verifying shared codes.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

python3 -m pip install --upgrade pyinstaller
python3 -m pip install -r application/requirements.txt

COMMON=(--noconfirm --clean --windowed --paths application)
# torch CUDA is unavailable on macOS; keep the bundle small.
TORCH=(--exclude-module torch --exclude-module torchvision --exclude-module torchaudio)

python3 -m PyInstaller "${COMMON[@]}" "${TORCH[@]}" --name "GPU Check" application/gpu_check.py
python3 -m PyInstaller "${COMMON[@]}" "${TORCH[@]}" --name "GPU Ops"   application/gpu_ops.py

# Server-address config beside each .app (edit before distributing).
cp packaging/gpuperf.config.example.json "dist/GPU Check.app/Contents/MacOS/gpuperf.config.json"
cp packaging/gpuperf.config.example.json "dist/GPU Ops.app/Contents/MacOS/gpuperf.config.json"

echo "Done. See dist/GPU Check.app and dist/GPU Ops.app"
echo "Edit the bundled gpuperf.config.json to set your backend URL."
