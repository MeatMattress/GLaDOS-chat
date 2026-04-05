@echo off
title GLaDOS Chat - First Time Setup
echo ============================================================
echo   GLaDOS Voice Chat - First Time Setup
echo ============================================================
echo.

cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

:: Check git
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] git not found. Install git and add to PATH.
    pause
    exit /b 1
)

:: Create venv if it doesn't exist
echo [1/3] Setting up virtual environment...
if not exist "venv" (
    python -m venv venv
)
call venv\Scripts\activate.bat
echo       Done.

:: Install Python dependencies
echo [2/3] Installing Python dependencies (this may take a while)...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo       Done.

:: Download models via cross-platform script
echo [3/3] Downloading models...
python setup_models.py %*

echo.
echo   Setup complete! Run "run.bat" to start GLaDOS Chat.
echo.
pause
