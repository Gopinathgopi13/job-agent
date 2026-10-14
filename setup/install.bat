@echo off
setlocal

rem First-time setup for Windows. Creates the virtual environment, installs
rem every Python dependency, and downloads the Chromium build Playwright
rem drives. Run this once; jobsprint.bat calls it automatically if you
rem haven't.
rem
rem NOTE: keep this file pure ASCII. cmd.exe parses batch files through the
rem console codepage, and a stray non-ASCII character (an em dash, say)
rem corrupts the parser and produces baffling "not recognized as an internal
rem or external command" errors on unrelated lines.

rem Repo root is one level up from this script.
cd /d "%~dp0.."

where python >nul 2>nul
if errorlevel 1 (
    echo Python 3.9+ is required but was not found on PATH.
    echo Install it from https://www.python.org/downloads/ and tick
    echo "Add python.exe to PATH" during setup.
    if not "%~1"=="--auto" pause
    exit /b 1
)

rem Cosmetic only: the real JOBSPRINT wordmark, in the same colours the app
rem uses once it's running. Never blocks setup - a terminal that can't show
rem it just prints whatever it prints and setup carries on regardless.
python setup\setup_banner.py 2>nul

if not exist "venv\Scripts\activate.bat" (
    echo [1/3] Creating the virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat

echo [2/3] Installing Python dependencies...
python -m pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo.
    echo Dependency install failed - see the error above.
    if not "%~1"=="--auto" pause
    exit /b 1
)

echo [3/3] Installing the Chromium browser ^(one-time, ~150MB^)...
python -m playwright install chromium
if errorlevel 1 (
    echo.
    echo Chromium install failed - check your internet connection and retry.
    if not "%~1"=="--auto" pause
    exit /b 1
)

echo. > venv\.setup_complete

rem Fingerprint requirements.txt so jobsprint.bat can tell, on a later run,
rem whether dependencies have changed since this install and the venv needs
rem rebuilding rather than just reused.
set "REQ_HASH="
for /f "skip=1 delims=" %%H in ('certutil -hashfile requirements.txt SHA256 2^>nul') do (
    if not defined REQ_HASH set "REQ_HASH=%%H"
)
>venv\.requirements.hash echo %REQ_HASH%

echo.
echo +------------------------------------------------------+
echo   Setup complete.
echo   Run jobsprint.bat whenever you want to apply.
echo +------------------------------------------------------+

if not "%~1"=="--auto" pause
