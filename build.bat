@echo off
setlocal enabledelayedexpansion

echo ============================================================
echo        Watermark Remover - Windows Build Automation
echo ============================================================

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not on PATH.
    pause
    exit /b 1
)

echo [1/5] Checking dependencies...
python -m pip install -r requirements-dev.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [2/5] Cleaning previous build artifacts...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/5] Running PyInstaller...
pyinstaller --clean --noconfirm WatermarkRemover.spec
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    pause
    exit /b 1
)

set DIST_DIR=dist\WatermarkRemover
if not exist "%DIST_DIR%\WatermarkRemover.exe" (
    echo [ERROR] WatermarkRemover.exe was not found in %DIST_DIR%.
    pause
    exit /b 1
)

echo [4/5] Structuring portable distribution...
if not exist "%DIST_DIR%\ffmpeg" mkdir "%DIST_DIR%\ffmpeg"
if not exist "%DIST_DIR%\models" mkdir "%DIST_DIR%\models"
if not exist "%DIST_DIR%\output" mkdir "%DIST_DIR%\output"
if not exist "%DIST_DIR%\temp" mkdir "%DIST_DIR%\temp"
if not exist "%DIST_DIR%\logs" mkdir "%DIST_DIR%\logs"

if exist "ffmpeg\ffmpeg.exe" (
    echo   - Copying bundled FFmpeg...
    copy /y "ffmpeg\ffmpeg.exe" "%DIST_DIR%\ffmpeg\" >nul
    copy /y "ffmpeg\ffprobe.exe" "%DIST_DIR%\ffmpeg\" >nul
)

for /f "delims=" %%i in ('python -c "import os, torchvision; print(os.path.dirname(torchvision.__file__))"') do set "TV_SRC=%%i"
if exist "%DIST_DIR%\_internal\torchvision" (
    copy /y "%TV_SRC%\*.pyd" "%DIST_DIR%\_internal\torchvision\" >nul 2>&1
    copy /y "%TV_SRC%\*.dll" "%DIST_DIR%\_internal\torchvision\" >nul 2>&1
)

if exist "models\ProPainter.pth" (
    echo   - Copying AI model weights...
    copy /y "models\*.pth" "%DIST_DIR%\models\" >nul
)

copy /y "LICENSE" "%DIST_DIR%\" >nul
copy /y "NOTICE_PROPAINTER.txt" "%DIST_DIR%\" >nul
copy /y "NOTICE_FFMPEG.txt" "%DIST_DIR%\" >nul
copy /y "README.md" "%DIST_DIR%\" >nul

echo ============================================================
echo [5/5] BUILD SUCCESSFUL!
echo Portable application is ready in: %DIST_DIR%
echo Run WatermarkRemover.exe to start.
echo ============================================================
