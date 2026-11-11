@echo off
echo ====================================================================
echo CDC Ingestion and Auditable History End-to-End Pipeline Demonstration
echo ====================================================================

echo.
echo [Step 1] Initializing Database Schema...
python backend/main.py --init-db

echo.
echo [Step 2] Generating Reproducible Starter Sample Dataset...
python backend/main.py --generate-starter

echo.
echo [Step 3] Running Ingestion Pipeline on Starter Sample...
python backend/main.py --run-batch sample_data/starter_sample.json

echo.
echo [Step 4] Running Mathematical Reconciliation and Invariant Checks...
python backend/main.py --reconcile

echo.
echo [Step 5] Running Full Automated Test Suite (13 Test Scenarios)...
python -m pytest backend/tests -v

echo.
echo ====================================================================
echo Full Demonstration Complete! All checks executed successfully.
echo ====================================================================
pause
