@echo off
echo ===================================================
echo Running CDC Pipeline Automated Tests (pytest)
echo ===================================================
python -m pytest backend/tests -v
pause
