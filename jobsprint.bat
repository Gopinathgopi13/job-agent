@echo off
setlocal enabledelayedexpansion

rem JobSprint - one-click launcher for Windows.
rem Double-click this file, or run "jobsprint.bat" from a terminal.
rem Dependencies install themselves the first time only, and only rebuild
rem again if requirements.txt changes or the venv looks broken.
rem
rem NOTE: keep this file pure ASCII - see the comment in setup\install.bat.

cd /d "%~dp0"

set NEED_SETUP=0
if not exist "venv\.setup_complete" set NEED_SETUP=1
if not exist "venv\Scripts\python.exe" set NEED_SETUP=1

if !NEED_SETUP! == 0 (
    set "OLD_HASH="
    if exist "venv\.requirements.hash" set /p OLD_HASH=<venv\.requirements.hash

    set "NEW_HASH="
    for /f "skip=1 delims=" %%H in ('certutil -hashfile requirements.txt SHA256 2^>nul') do (
        if not defined NEW_HASH set "NEW_HASH=%%H"
    )

    if not "!OLD_HASH!"=="!NEW_HASH!" set NEED_SETUP=1
)

if !NEED_SETUP! == 1 (
    if exist "venv" (
        echo Dependencies changed since the last run - rebuilding the virtual environment...
        rmdir /s /q venv
    )
    call setup\install.bat --auto
    if errorlevel 1 exit /b 1
    echo.
) else (
    echo Environment already set up - launching JobSprint...
    call venv\Scripts\activate.bat
)

rem --apply refreshes the knowledge base itself before signing in, so there
rem is no separate training step here.
python -m jobsprint --apply

pause
