@echo off
setlocal enabledelayedexpansion
title Harness2 Launcher

cd /d "%~dp0"

echo ===================================================
echo               Harness2 Launcher
echo ===================================================
echo.

:: Check for virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo [.venv not detected. Attempting automatic setup with uv...]
    where uv >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] 'uv' is not installed or not in PATH.
        echo Please install uv or create a Python 3.12 virtual environment at .venv.
        pause
        exit /b 1
    )
    echo Creating virtual environment with Python 3.12...
    uv venv --python 3.12 .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create .venv.
        pause
        exit /b 1
    )
    echo Installing package and dependencies in editable mode...
    uv pip install -e ".[render]"
    if %errorlevel% neq 0 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
)

:: Activate virtual environment
call ".venv\Scripts\activate.bat"

:: If arguments were passed directly to start.bat, execute them
if not "%~1"=="" (
    if /i "%~1"=="demo" (
        echo Running Harness2 local demo...
        harness2-demo.exe --output runs\demo --k 2
        goto end
    )
    if /i "%~1"=="test" (
        echo Running tests...
        python -m unittest tests/test_workflow.py
        goto end
    )
    if /i "%~1"=="check" (
        shift
        harness2-check.exe %*
        goto end
    )
    REM General pass-through
    %*
    goto end
)

:menu
echo Please select an option:
echo [1] Run Local Demo (Deterministic, no API keys needed)
echo [2] Run Workflow Regressions / Tests
echo [3] Run Benchmark Configuration Check (harness2-check)
echo [4] Setup a Benchmark (harness2-setup)
echo [5] Start Codex LiteLLM Bridge (harness2-bridge)
echo [6] Open Activated Command Prompt
echo [7] Exit
echo(
set "choice="
set /p choice="Enter choice [1-7]: "
if not defined choice goto end

if "!choice!"=="1" (
    echo(
    echo Running local demo...
    harness2-demo.exe --output runs\demo --k 2
    echo(
    pause
    goto menu
)
if "!choice!"=="2" (
    echo(
    echo Running unit tests...
    python -m unittest tests/test_workflow.py
    echo(
    pause
    goto menu
)
if "!choice!"=="3" (
    echo(
    set /p bname="Enter benchmark name (jb, lab, wb): "
    harness2-check.exe --bench !bname!
    echo(
    pause
    goto menu
)
if "!choice!"=="4" (
    echo(
    set /p bname="Enter benchmark name (jb, lab, wb): "
    harness2-setup.exe !bname!
    echo(
    pause
    goto menu
)
if "!choice!"=="5" (
    echo(
    echo Starting LiteLLM Bridge...
    harness2-bridge.exe
    pause
    goto menu
)
if "!choice!"=="6" (
    echo(
    echo Starting activated shell. Type 'exit' to return.
    cmd /k
    goto menu
)
if "!choice!"=="7" (
    goto end
)

echo Invalid choice, please try again.
echo(
goto menu

:end
endlocal
