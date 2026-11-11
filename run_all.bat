@echo off
setlocal EnableDelayedExpansion
title CDC Pipeline - Run All Tests and Demo
color 0A

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
            echo     Found Python: %%~P
        )
    )
)
if "!PYTHON_CMD!"=="" (
    for /f "tokens=*" %%i in ('where python 2^>nul') do (
        if "!PYTHON_CMD!"=="" set PYTHON_CMD=%%i
    )
    if not "!PYTHON_CMD!"=="" echo     Found via PATH: !PYTHON_CMD!
)
if "!PYTHON_CMD!"=="" (
    echo [ERROR] No Python interpreter found. Please run setup_and_run.bat first.
    pause
    exit /b 1
)

set PYTHONPATH=%~dp0

echo.
echo ====================================================================
echo   CDC Ingestion - Auditable History End-to-End Pipeline Demo
echo ====================================================================
echo.

echo [Step 1/5] Initializing Database Schema...
"!PYTHON_CMD!" backend\main.py --init-db
echo.

echo [Step 2/5] Generating Reproducible Starter Sample Dataset...
"!PYTHON_CMD!" backend\main.py --generate-starter
echo.

echo [Step 3/5] Running Ingestion Pipeline on Starter Sample...
"!PYTHON_CMD!" backend\main.py --run-batch sample_data\starter_sample.json
echo.

echo [Step 4/5] Running Mathematical Reconciliation and Invariant Checks...
"!PYTHON_CMD!" backend\main.py --reconcile
echo.

echo [Step 5/5] Running Full Automated Test Suite (13 Test Scenarios)...
"!PYTHON_CMD!" -m pytest backend/tests -v --tb=short
echo.

echo ====================================================================
echo   Full Demo Complete! To start the live dashboard: start_dashboard.bat
echo ====================================================================
pause
