@echo off
setlocal enabledelayedexpansion
title Omni-3D Studio - Image-to-3D Generator
color 0B

echo =================================================================
echo   [OMNI-3D STUDIO] Image-to-3D Generator Application
echo =================================================================
echo.

cd /d "%~dp0"

:: 1. Locate Python in .venv
if exist "..\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=..\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

:: 2. Check Ollama
echo [*] Checking Ollama server (http://localhost:11434)...
curl -s http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Ollama does not seem to be running on http://localhost:11434!
    echo           Make sure Ollama is started for AI token generation.
    echo.
) else (
    echo [OK] Ollama is active.
)

:: 3. Check Blender
echo [*] Checking Blender 5.2 LTS...
if exist "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" (
    echo [OK] Blender 5.2 LTS detected.
) else (
    echo [WARNING] Blender 5.2 not found at default path. Will scan system.
)

echo.
echo [*] Starting Omni-3D Studio on http://localhost:8766...
echo [*] Opening browser...
echo.

"%PYTHON_EXE%" app.py --port 8766

pause
