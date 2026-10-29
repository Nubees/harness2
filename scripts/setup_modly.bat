@echo off
title Modly AI Integration Setup (lightningpixel/modly)
echo =====================================================================
echo  Omni-3D Studio - Modly Local AI Integration (lightningpixel/modly)
echo =====================================================================
echo.
echo Modly provides local offline 3D AI neural mesh generation:
echo - Hunyuan3D-2 Mini, TripoSG, TRELLIS.2 GGUF
echo - Runs 100%% offline on an NVIDIA GPU (8GB+ VRAM recommended)
echo - Zero cloud fees, zero API keys
echo.

set TARGET_DIR=%~dp0..\dependencies\modly
if not exist "%~dp0..\dependencies" mkdir "%~dp0..\dependencies"

if exist "%TARGET_DIR%\.git" (
    echo [OK] Modly repository already found in %TARGET_DIR%
) else (
    echo [1/3] Cloning Modly from GitHub...
    git clone https://github.com/lightningpixel/modly.git "%TARGET_DIR%"
    if errorlevel 1 (
        echo [ERROR] Git clone failed. Please make sure git is installed.
        pause
        exit /b 1
    )
)

echo.
echo [2/3] Setting up Modly Python backend environment...
cd /d "%TARGET_DIR%\api"
if not exist ".venv" (
    echo Creating virtual environment for Modly...
    python -m venv .venv
)
call .venv\Scripts\activate.bat
echo Installing Modly dependencies...
pip install -r requirements.txt

echo.
echo =====================================================================
echo  [SUCCESS] Modly is ready!
echo  To launch Modly, run launcher.bat in %TARGET_DIR%
echo  Omni-3D Studio will automatically detect Modly on http://127.0.0.1:8000
echo =====================================================================
pause
