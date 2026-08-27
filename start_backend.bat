@echo off
REM -----------------------------------------------
REM AFRICA RESQ - one-click backend start (Windows)
REM Runs:  python run_api.py
REM Dashboard: http://localhost:8000/map
REM API docs:  http://localhost:8000/docs
REM -----------------------------------------------

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Install Python 3.10+ first.
    pause
    exit /b 1
)

python run_api.py
pause