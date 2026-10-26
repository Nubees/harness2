@echo off
setlocal enabledelayedexpansion
title Harness2 - Live Dual-Shift Dashboard

echo ============================================================
echo   HARNESS^2 DUAL-SHIFT TELEMETRY DASHBOARD
echo ============================================================
echo.

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Please run start.bat first.
    pause
    exit /b 1
)

echo Starting Telemetry Server on http://localhost:8765 ...
start "" http://localhost:8765/dashboard
.venv\Scripts\python.exe scripts\telemetry_server.py --port 8765

pause
