@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0.venv\Scripts\python.exe" (
    echo [ERROR] %~dp0.venv\Scripts\python.exe not found.
    echo Please set up the virtual environment first.
    pause
    exit /b 1
)

if not exist "%~dp0app\main.py" (
    echo [ERROR] %~dp0app\main.py not found.
    pause
    exit /b 1
)

echo Starting app...
"%~dp0.venv\Scripts\python.exe" "%~dp0app\main.py"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%.
    pause
    exit /b %errorlevel%
)
