"""Single, writable, per-machine app-data location.

Storage used to be CWD-relative (`./jobsprint/data/...`), which only worked
because the app was always launched from the repo root. That breaks the
moment this runs as an installed .exe from a Start Menu shortcut — the
working directory could be anything, and the install directory itself
(e.g. Program Files) usually isn't writable. Every path below is absolute
and resolved once, at import time.
"""

import os
import shutil
import sys

APP_NAME = "JobSprint"
_LEGACY_APP_NAME = "JobSprint"  # pre-rename; migrated once, on first run


def _data_dir(app_name: str) -> str:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(root, app_name)
    return os.path.join(os.path.expanduser("~"), f".{app_name.lower()}")


def _migrate_legacy_data(new_dir: str):
    """Carry an existing JobSprint data folder over to the new name.

    The profile, knowledge base (including every answer taught by hand) and
    application history all live here — renaming the app must not silently
    orphan them behind a folder nothing reads any more.
    """
    old_dir = _data_dir(_LEGACY_APP_NAME)
    if old_dir == new_dir or os.path.exists(new_dir) or not os.path.isdir(old_dir):
        return
    try:
        shutil.copytree(old_dir, new_dir)
    except Exception:
        # Never let a migration problem stop the app from starting — worst
        # case it begins with an empty knowledge base, which --train rebuilds.
        pass


APP_DATA_DIR = _data_dir(APP_NAME)
_migrate_legacy_data(APP_DATA_DIR)

PROFILE_PATH = os.path.join(APP_DATA_DIR, "profile.json")
PREFS_PATH = os.path.join(APP_DATA_DIR, "preferences.json")
DB_PATH = os.path.join(APP_DATA_DIR, "app.db")
EXCEL_PATH = os.path.join(APP_DATA_DIR, "applications.xlsx")
RESUME_DIR = os.path.join(APP_DATA_DIR, "resume_uploads")
LOGS_DIR = os.path.join(APP_DATA_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(APP_DATA_DIR, "screenshots")

for _dir in (APP_DATA_DIR, RESUME_DIR, LOGS_DIR, SCREENSHOTS_DIR):
    os.makedirs(_dir, exist_ok=True)
