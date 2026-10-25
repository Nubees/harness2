@echo off
setlocal enabledelayedexpansion
title Harness2 - Google Vertex AI Route

cd /d "%~dp0"

echo ===================================================
echo        Harness2 - Google Vertex AI Route
echo ===================================================
echo.

:: Ensure virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo [.venv not detected. Attempting setup with uv...]
    where uv >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] 'uv' is not installed or not in PATH.
        pause
        exit /b 1
    )
    uv venv --python 3.12 .venv
    uv pip install -e ".[render]"
)
call ".venv\Scripts\activate.bat"

:: Quick command line shortcut handling
if /i "%~1"=="demo" (
    echo Running Harness2 local demo...
    harness2-demo.exe --output runs\demo --k 2
    goto end
)

:: Check Google Cloud CLI
where gcloud >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARNING] 'gcloud' CLI was not found on PATH.
    echo Please ensure Google Cloud SDK is installed and in your PATH.
    echo.
) else (
    echo Checking Application Default Credentials...
    gcloud auth application-default print-access-token >nul 2>&1
    if %errorlevel% neq 0 (
        echo.
        echo [ACTION REQUIRED] Application Default Credentials are not active.
        echo Opening gcloud auth application-default login...
        gcloud auth application-default login
    ) else (
        echo [OK] Google Application Default Credentials found.
    )
)

:: Project ID handling
if "%GOOGLE_CLOUD_PROJECT%"=="" (
    for /f "tokens=*" %%i in ('gcloud config get-value project 2^>nul') do set DETECTED_PROJECT=%%i
    if not "!DETECTED_PROJECT!"=="" if not "!DETECTED_PROJECT!"=="(unset)" (
        set GOOGLE_CLOUD_PROJECT=!DETECTED_PROJECT!
    )
)

if "%GOOGLE_CLOUD_PROJECT%"=="" (
    if "%~1"=="" (
        echo.
        set /p GOOGLE_CLOUD_PROJECT="Enter your Google Cloud Project ID: "
    )
)

echo.
echo Active Project: %GOOGLE_CLOUD_PROJECT%
set GOOGLE_CLOUD_LOCATION=global
set HARNESS2_SOLVER_MODEL=google-vertex/gemini-2.5-flash
set HARNESS2_IMPROVER_MODEL=google-vertex/gemini-2.5-flash
set HARNESS2_JUDGE_MODEL=gemini-2.5-flash

echo Solver Model:   %HARNESS2_SOLVER_MODEL%
echo Improver Model: %HARNESS2_IMPROVER_MODEL%
echo Judge Model:    %HARNESS2_JUDGE_MODEL%
echo.

:: Argument pass-through
if not "%~1"=="" (
    %*
    goto end
)

:menu
echo Select an action:
echo [1] Run Benchmark Check (harness2-check)
echo [2] Setup Benchmark (harness2-setup)
echo [3] Run Benchmark Task (Dry Run preview)
echo [4] Run Benchmark Task (Live Run)
echo [5] Run Local Deterministic Demo
echo [6] Open Activated Shell
echo [7] Exit
echo.
set "choice="
set /p choice="Enter choice [1-7]: "
if not defined choice goto end

if "!choice!"=="1" (
    echo.
    set /p bname="Enter benchmark (jb / lab / wb): "
    harness2-check.exe --bench !bname!
    echo.
    pause
    goto menu
)
if "%choice%"=="2" (
    echo.
    set /p bname="Enter benchmark to setup (jb / lab / wb): "
    harness2-setup.exe !bname!
    echo.
    pause
    goto menu
)
if "%choice%"=="3" (
    echo.
    set /p bname="Enter benchmark (jb / lab / wb): "
    harness2.exe --bench !bname! --k 1 --mode parallel --max-tasks 1 --dry-run
    echo.
    pause
    goto menu
)
if "%choice%"=="4" (
    echo.
    set /p bname="Enter benchmark (jb / lab / wb): "
    echo Starting live run on !bname! with Google Vertex AI...
    harness2.exe --bench !bname! --k 1 --mode parallel --max-tasks 1
    harness2-judge.exe --bench !bname! --k 1 --mode parallel
    harness2-report.exe --bench !bname! --k 1 --mode parallel
    echo.
    pause
    goto menu
)
if "%choice%"=="5" (
    echo.
    harness2-demo.exe --output runs\demo --k 2
    echo.
    pause
    goto menu
)
if "%choice%"=="6" (
    echo.
    echo Shell ready with Google Vertex AI settings. Type 'exit' to return.
    cmd /k
    goto menu
)
if "%choice%"=="7" (
    goto end
)

echo Invalid choice, please try again.
goto menu

:end
endlocal
