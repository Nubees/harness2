@echo off
setlocal enabledelayedexpansion
title Harness2 - Ollama Route

cd /d "%~dp0"

echo ===================================================
echo             Harness2 - Ollama Route
echo ===================================================
echo(

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

:select_model
:: Ensure runs folder exists for temp output
if not exist "runs" mkdir "runs"

:: Check and select model via PowerShell helper if not set or if requested
if "%OLLAMA_MODEL%"=="" (
    if exist "scripts\select_ollama_model.ps1" (
        powershell -ExecutionPolicy Bypass -File scripts\select_ollama_model.ps1 -OutputFile runs\_selected_ollama.txt
        if exist "runs\_selected_ollama.txt" (
            set /p OLLAMA_MODEL=<runs\_selected_ollama.txt
            del runs\_selected_ollama.txt >nul 2>&1
        )
    )
)

if "%OLLAMA_MODEL%"=="" set OLLAMA_MODEL=kimi-k2.7-code:cloud

set OLLAMA_BASE_URL=http://localhost:11434/v1

:: Configure environment for Harness2 components
set HARNESS2_JUDGE_BASE_URL=%OLLAMA_BASE_URL%
set HARNESS2_JUDGE_API_KEY=ollama
set HARNESS2_JUDGE_MODEL=%OLLAMA_MODEL%

set HARNESS2_CODEX_BASE_URL=%OLLAMA_BASE_URL%
set HARNESS2_CODEX_CONTAINER_URL=%OLLAMA_BASE_URL%
set HARNESS2_CODEX_API_KEY=ollama
set HARNESS2_CODEX_MODEL=%OLLAMA_MODEL%

set HARNESS2_SOLVER_MODEL=ollama/%OLLAMA_MODEL%
set HARNESS2_IMPROVER_MODEL=ollama/%OLLAMA_MODEL%

echo(
echo ===================================================
echo  Active Model:      %OLLAMA_MODEL%
echo  API Base URL:      %OLLAMA_BASE_URL%
echo  Solver / Improver: %HARNESS2_SOLVER_MODEL%
echo  Judge Model:       %HARNESS2_JUDGE_MODEL%
echo ===================================================
echo(
echo READY-TO-USE CLI COMMANDS FOR THIS MODEL:
echo   - Preview benchmark tasks (safe / dry run):
echo       harness2 --bench jb --dry-run
echo   - Run 1 live task with this model (Codex substrate):
echo       harness2 --bench jb --substrate cx --k 1 --mode parallel --max-tasks 1
echo   - Setup benchmark dependencies (e.g. JobBench):
echo       harness2-setup jb
echo   - Run local deterministic demo:
echo       harness2-demo --output runs/demo --k 2
echo(

:: Argument pass-through
if not "%~1"=="" (
    %*
    goto end
)

:menu
echo Select an option:
echo [1] Start Interactive Harnessed AI Chat (Chat with !OLLAMA_MODEL!) [DEFAULT - Press Enter]
echo [2] Start Raw Ollama Chat (ollama run !OLLAMA_MODEL!)
echo [3] Open Command Prompt Shell (CLI)
echo [4] Run Task Preview (harness2 --dry-run)
echo [5] Run 1 Live Benchmark Task (--substrate cx)
echo [6] Setup Benchmark (harness2-setup jb/lab/wb)
echo [7] Switch / Rescan Ollama Model (Local and Cloud)
echo [8] Run Local Deterministic Demo
echo [9] Exit
echo(
set "choice=1"
set /p choice="Enter choice [1-9, Default 1]: "

if "!choice!"=="1" (
    echo(
    python scripts\harness_chat.py !OLLAMA_MODEL!
    echo(
    pause
    goto menu
)
if "!choice!"=="2" (
    echo(
    echo Launching native Ollama chat for !OLLAMA_MODEL!...
    ollama run !OLLAMA_MODEL!
    echo(
    pause
    goto menu
)
if "!choice!"=="3" (
    echo(
    echo ===================================================
    echo Interactive CLI Shell Ready for !OLLAMA_MODEL!
    echo All environment variables and harness tools are active.
    echo Type 'exit' to return to menu.
    echo ===================================================
    echo(
    set "PROMPT=[Ollama:!OLLAMA_MODEL!] $P$G"
    cmd /k
    goto menu
)
if "!choice!"=="4" (
    echo(
    set /p bname="Enter benchmark (jb / lab / wb) [Default: jb]: "
    if "!bname!"=="" set bname=jb
    harness2.exe --bench !bname! --k 1 --mode parallel --max-tasks 1 --dry-run
    echo(
    pause
    goto menu
)
if "!choice!"=="5" (
    echo(
    set /p bname="Enter benchmark (jb / lab / wb) [Default: jb]: "
    if "!bname!"=="" set bname=jb
    echo Running live task with !OLLAMA_MODEL! via Codex substrate...
    harness2.exe --bench !bname! --substrate cx --k 1 --mode parallel --max-tasks 1
    harness2-judge.exe --bench !bname! --substrate cx --k 1 --mode parallel
    harness2-report.exe --bench !bname! --substrate cx --k 1 --mode parallel
    echo(
    pause
    goto menu
)
if "!choice!"=="6" (
    echo(
    set /p bname="Enter benchmark to setup (jb / lab / wb) [Default: jb]: "
    if "!bname!"=="" set bname=jb
    harness2-setup.exe !bname!
    echo(
    pause
    goto menu
)
if "!choice!"=="7" (
    set OLLAMA_MODEL=
    goto select_model
)
if "!choice!"=="8" (
    echo(
    harness2-demo.exe --output runs\demo --k 2
    echo(
    pause
    goto menu
)
if "!choice!"=="9" (
    goto end
)

echo Invalid choice, please try again.
goto menu

:end
endlocal
