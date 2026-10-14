#!/usr/bin/env bash
# First-time setup for macOS / Linux / Ubuntu. Creates the virtual
# environment, installs every Python dependency, and downloads the Chromium
# build Playwright drives. Run this once; jobsprint.sh calls it
# automatically if you haven't.
set -e

# Repo root is one level up from this script.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PYTHON_BIN="python3"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || PYTHON_BIN="python"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
    echo "Python 3.9+ is required but was not found on PATH."
    echo "Install it from https://www.python.org/downloads/, or via your"
    echo "package manager (e.g. 'sudo apt install python3 python3-venv')."
    exit 1
}

# Cosmetic only: the real JOBSPRINT wordmark, in the same colours the app
# uses once it's running. Never blocks setup.
"$PYTHON_BIN" setup/setup_banner.py 2>/dev/null || true

if [ ! -d "venv" ]; then
    echo "[1/3] Creating the virtual environment..."
    "$PYTHON_BIN" -m venv venv
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "[2/3] Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "[3/3] Installing the Chromium browser (one-time, ~150MB)..."
python -m playwright install chromium

touch venv/.setup_complete

# Fingerprint requirements.txt so jobsprint.sh can tell, on a later run,
# whether dependencies have changed since this install and the venv needs
# rebuilding rather than just reused.
if command -v sha256sum >/dev/null 2>&1; then
    sha256sum requirements.txt | cut -d' ' -f1 > venv/.requirements.hash
elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 requirements.txt | cut -d' ' -f1 > venv/.requirements.hash
fi

echo
echo "+------------------------------------------------------+"
echo "  Setup complete."
echo "  Run ./jobsprint.sh whenever you want to apply."
echo "+------------------------------------------------------+"
echo
echo "On a minimal or server Linux install, if Chromium later fails to launch"
echo "with a missing-library error, also run:"
echo "  python -m playwright install-deps chromium   # needs sudo"
