"""PyInstaller entry point. jobsprint/desktop.py uses package-relative
imports (`from . import paths`, etc.), which only work if it's imported as
part of the `jobsprint` package rather than run directly as a standalone
script — this tiny top-level script is what PyInstaller actually
analyzes/bundles, so `jobsprint` gets frozen in as a normal importable
package.
"""

import os
import sys

if sys.stdout is None or sys.stderr is None:
    # A windowed (console=False) build has no stdio streams at all — several
    # dependencies (uvicorn's logging, faulthandler, etc.) still try to
    # write to them at import/startup time and crash with an unhandled
    # AttributeError on None.write(...) if there's nowhere real to go. Give
    # them a real file instead of silently dying before any window opens.
    _log_dir = os.path.join(os.environ.get("LOCALAPPDATA") or ".", "JobSprint")
    os.makedirs(_log_dir, exist_ok=True)
    _log_file = open(os.path.join(_log_dir, "app_stdio.log"), "a", buffering=1, encoding="utf-8")
    sys.stdout = _log_file
    sys.stderr = _log_file

from jobsprint.desktop import main

if __name__ == "__main__":
    main()
