@echo off
echo ===================================================
echo Starting CDC Pipeline Backend and UI Dashboard
echo ===================================================
echo Opening http://localhost:8000 in your browser...
start http://localhost:8000
python scripts/start_server.py
pause
