# PowerShell Build Script for Watermark Remover
# Creates a portable Windows distribution in dist\WatermarkRemover\
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "       Watermark Remover - Windows Build Automation         " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Check Python
$pyVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python was not found on PATH. Please install Python 3.9+."
}
Write-Host "[1/5] Detected Python: $pyVersion" -ForegroundColor Green

# 2. Check and install dependencies
Write-Host "[2/5] Checking and installing dependencies from requirements-dev.txt..." -ForegroundColor Yellow
python -m pip install -r requirements-dev.txt

# 3. Clean prior builds
Write-Host "[3/5] Cleaning prior build artifacts..." -ForegroundColor Yellow
Remove-Item -Path "build", "dist" -Recurse -Force -ErrorAction SilentlyContinue

# 4. Run PyInstaller
Write-Host "[4/5] Building Windows Portable Executable with PyInstaller..." -ForegroundColor Yellow
pyinstaller --clean --noconfirm WatermarkRemover.spec

$distApp = "dist\WatermarkRemover"
if (-not (Test-Path "$distApp\WatermarkRemover.exe")) {
    Write-Error "Build failed: WatermarkRemover.exe was not created in $distApp"
}

# 5. Populate portable directory assets
Write-Host "[5/5] Structuring portable distribution folder..." -ForegroundColor Yellow

# Copy bundled FFmpeg
if (Test-Path "ffmpeg\ffmpeg.exe") {
    Write-Host "  -> Copying bundled FFmpeg binaries..."
    New-Item -ItemType Directory -Force -Path "$distApp\ffmpeg" | Out-Null
    Copy-Item "ffmpeg\ffmpeg.exe" "$distApp\ffmpeg\" -Force
    Copy-Item "ffmpeg\ffprobe.exe" "$distApp\ffmpeg\" -Force
}

# Copy propainter package into _internal
Write-Host "  -> Copying propainter module into _internal..."
Copy-Item -Path "propainter" -Destination "$distApp\_internal\" -Recurse -Force

# Ensure torchvision C-extensions are copied into _internal
$tvSrc = python -c "import os, torchvision; print(os.path.dirname(torchvision.__file__))"
$tvDst = "$distApp\_internal\torchvision"
if (Test-Path $tvDst) {
    Copy-Item "$tvSrc\*.pyd" $tvDst -Force
    Copy-Item "$tvSrc\*.dll" $tvDst -Force
}

# Copy model weights if present
if (Test-Path "models\ProPainter.pth") {
    Write-Host "  -> Copying AI model weights to portable models folder..."
    New-Item -ItemType Directory -Force -Path "$distApp\models" | Out-Null
    Copy-Item "models\*.pth" "$distApp\models\" -Force
} else {
    New-Item -ItemType Directory -Force -Path "$distApp\models" | Out-Null
    Write-Host "  -> Note: Model weights will be downloaded on first run via GUI." -ForegroundColor Cyan
}

# Create output, temp, logs directories
New-Item -ItemType Directory -Force -Path "$distApp\output", "$distApp\temp", "$distApp\logs" | Out-Null

# Copy Documentation & Licenses
Copy-Item "LICENSE", "NOTICE_PROPAINTER.txt", "NOTICE_FFMPEG.txt", "README.md" "$distApp\" -Force

Write-Host "============================================================" -ForegroundColor Green
Write-Host "  SUCCESS! Portable application build completed." -ForegroundColor Green
Write-Host "  Location: $PWD\$distApp" -ForegroundColor Green
Write-Host "  Executable: $PWD\$distApp\WatermarkRemover.exe" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
