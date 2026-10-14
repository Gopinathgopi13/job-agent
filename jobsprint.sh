#!/usr/bin/env bash
# JobSprint - one-click launcher for macOS / Linux / Ubuntu.
# Double-click it from a file manager (make it executable first:
# chmod +x jobsprint.sh), or run "./jobsprint.sh" from a terminal.
# Dependencies install themselves the first time only.
set -e

cd "$(dirname "${BASH_SOURCE[0]}")"

# Dependencies install themselves the first time only, and only rebuild
# again if requirements.txt changes or the venv looks broken.
NEED_SETUP=0
if [ ! -f "venv/.setup_complete" ] || [ ! -f "venv/bin/python" ]; then
    NEED_SETUP=1
fi

if [ "$NEED_SETUP" -eq 0 ]; then
    if command -v sha256sum >/dev/null 2>&1; then
        CURRENT_HASH=$(sha256sum requirements.txt | cut -d' ' -f1)
    elif command -v shasum >/dev/null 2>&1; then
        CURRENT_HASH=$(shasum -a 256 requirements.txt | cut -d' ' -f1)
    else
        CURRENT_HASH=""
    fi
    STORED_HASH=$(cat venv/.requirements.hash 2>/dev/null || echo "")
    if [ "$CURRENT_HASH" != "$STORED_HASH" ]; then
        NEED_SETUP=1
    fi
fi

if [ "$NEED_SETUP" -eq 1 ]; then
    if [ -d "venv" ]; then
        echo "Dependencies changed since the last run - rebuilding the virtual environment..."
        rm -rf venv
    fi
    ./setup/install.sh
    echo
else
    echo "Environment already set up - launching JobSprint..."
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

# --apply refreshes the knowledge base itself before signing in, so there is
# no separate training step here.
python -m jobsprint --apply
