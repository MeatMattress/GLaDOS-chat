@echo off
title GLaDOS Voice Chat
cd /d "%~dp0"

:: Check setup was run
if not exist "venv" (
    echo First time? Running setup...
    call setup.bat
)

:: Activate venv
call venv\Scripts\activate.bat

:: Launch GUI (use --cli for terminal mode)
if "%1"=="--cli" (
    python glados_chat.py
) else (
    python glados_gui.py
)
