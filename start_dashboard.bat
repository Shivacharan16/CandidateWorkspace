@echo off
setlocal EnableDelayedExpansion
title CDC Pipeline - Start Dashboard
color 0B

:: ── Find Python ────────────────────────────────────────────────
set PYTHON_CMD=
for %%P in (
    "C:\Users\bshiv\anaconda3\python.exe"
    "C:\ProgramData\Anaconda3\python.exe"
    "C:\Program Files\Python313\python.exe"
    "C:\Program Files\Python312\python.exe"
    "C:\Program Files\Python311\python.exe"
    "C:\Program Files\Python310\python.exe"
) do (
    if "!PYTHON_CMD!"=="" (
        if exist %%P (
            set PYTHON_CMD=%%~P
        )
    )
)
if "!PYTHON_CMD!"=="" (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        if "!PYTHON_CMD!"=="" set PYTHON_CMD=%%i
    )
)
if "!PYTHON_CMD!"=="" (
    echo [ERROR] Python not found. Run setup_and_run.bat first.
    pause
    exit /b 1
)

set PYTHONPATH=%~dp0

echo ============================================================
echo   CDC Pipeline Dashboard  - Starting Server
echo ============================================================
echo.
echo   Dashboard URL : http://localhost:8000
echo   API Docs      : http://localhost:8000/docs
echo.
echo   Press Ctrl+C to stop the server.
echo ============================================================
echo.

"!PYTHON_CMD!" scripts\start_server.py
pause
