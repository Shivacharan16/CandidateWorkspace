@echo off
setlocal EnableDelayedExpansion
title CDC Pipeline - Run Tests

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
    if "!PYTHON_CMD!"=="" if exist %%P set PYTHON_CMD=%%~P
)
if "!PYTHON_CMD!"=="" (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        if "!PYTHON_CMD!"=="" set PYTHON_CMD=%%i
    )
)

set PYTHONPATH=%~dp0

echo Running CDC Pipeline Test Suite...
echo.
"!PYTHON_CMD!" -m pytest backend/tests -v --tb=short
echo.
pause
