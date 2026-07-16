<#
Build the Windows desktop apps (GPU Check + GPU Ops) into standalone folders
under dist/. Run from a Windows machine with Python 3.11+ installed.

    # small build (info + sensors + accounts; benchmark disabled):
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1

    # full build (bundles torch+CUDA -> large, real benchmark works):
    powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -WithTorch

Output: dist\GPU Check\  and  dist\GPU Ops\  — zip each folder to distribute.
Users edit gpuperf.config.json (placed beside the .exe) to point at the server.
#>
param([switch]$WithTorch)
$ErrorActionPreference = "Stop"

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

python -m pip install --upgrade pyinstaller
python -m pip install -r application\requirements.txt

# --collect-all pip: the lite build has no torch and installs the benchmark
# engine on demand via in-process pip, so pip must be bundled.
$common = @("--noconfirm", "--clean", "--windowed", "--paths", "application", "--collect-all", "pip")
if ($WithTorch) {
    $torch = @("--collect-all", "torch")
    Write-Host "Building WITH torch (large, benchmark bundled)..." -ForegroundColor Green
} else {
    $torch = @("--exclude-module", "torch", "--exclude-module", "torchvision", "--exclude-module", "torchaudio")
    Write-Host "Building lite (small; engine downloaded on first benchmark)..." -ForegroundColor Yellow
}

python -m PyInstaller @common @torch --name "GPU Check" application\gpu_check.py
python -m PyInstaller @common @torch --name "GPU Ops"   application\gpu_ops.py

# Drop a server-address config beside each executable (edit before shipping).
Copy-Item packaging\gpuperf.config.example.json "dist\GPU Check\gpuperf.config.json" -Force
Copy-Item packaging\gpuperf.config.example.json "dist\GPU Ops\gpuperf.config.json" -Force

Write-Host "Done. See dist\GPU Check\ and dist\GPU Ops\." -ForegroundColor Green
Write-Host "Edit the gpuperf.config.json in each folder to set your backend URL." -ForegroundColor Green
