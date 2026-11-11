@echo off
setlocal EnableDelayedExpansion
title CDC Pipeline - Full Auto Setup and Run
color 0A

echo ============================================================
echo   CDC Ingestion - Auditable History Pipeline
echo   Auto-Setup, Test, and Demo Runner
echo ============================================================
echo.

:: ── Step 0: Find a working Python interpreter ────────────────
set PYTHON_CMD=
echo [0/6] Detecting Python interpreter...

:: Try each known Python location in priority order
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
            echo     Found: %%~P
        )
    )
)

:: Fallback: use system python
if "!PYTHON_CMD!"=="" (
    where python >nul 2>&1
    if !errorlevel! == 0 (
        for /f "tokens=*" %%i in ('where python 2^>nul') do (
            if "!PYTHON_CMD!"=="" (
                set PYTHON_CMD=%%i
            )
        )
        echo     Found via PATH: !PYTHON_CMD!
    )
)

if "!PYTHON_CMD!"=="" (
    echo [ERROR] No Python interpreter found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

echo     Using: !PYTHON_CMD!

:: Verify Python version
"!PYTHON_CMD!" -c "import sys; v=sys.version_info; exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
if !errorlevel! NEQ 0 (
    echo [WARN] Python version may be < 3.10. Attempting anyway...
)

echo.

:: ── Step 1: Install dependencies ──────────────────────────────
echo [1/6] Installing Python dependencies...
"!PYTHON_CMD!" -m pip install -q --upgrade pip
"!PYTHON_CMD!" -m pip install -q -r requirements.txt
if !errorlevel! NEQ 0 (
    echo [ERROR] Dependency installation failed. Check your internet connection.
    pause
    exit /b 1
)
echo     All dependencies installed OK.
echo.

:: ── Step 2: Set PYTHONPATH ────────────────────────────────────
set PYTHONPATH=%~dp0
echo [2/6] PYTHONPATH set to: %PYTHONPATH%
echo.

:: ── Step 3: Initialize DB ─────────────────────────────────────
echo [3/6] Initializing Database Schema...
"!PYTHON_CMD!" backend\main.py --init-db
echo.

:: ── Step 4: Run Automated Tests ──────────────────────────────
echo [4/6] Running Automated Test Suite (13 scenarios)...
"!PYTHON_CMD!" -m pytest backend/tests -v --tb=short
if !errorlevel! NEQ 0 (
    echo [WARN] Some tests failed. Review above output.
) else (
    echo     All tests PASSED.
)
echo.

:: ── Step 5: Ingest Starter Sample ─────────────────────────────
echo [5/6] Generating and Ingesting Starter Sample Dataset...
"!PYTHON_CMD!" backend\main.py --generate-starter
"!PYTHON_CMD!" backend\main.py --run-batch sample_data\starter_sample.json
echo.

:: ── Step 6: Reconciliation ─────────────────────────────────────
echo [6/6] Running Reconciliation and Quality Audit...
"!PYTHON_CMD!" backend\main.py --reconcile
echo.

echo ============================================================
echo   Full Demo Complete! 
echo   To start the live dashboard, run: start_dashboard.bat
echo ============================================================
pause
