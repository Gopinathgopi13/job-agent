"""First-run Chromium provisioning.

Playwright manages its browser binaries in a cache separate from pip
packages — not something worth bundling into the installer (a ~150MB
download that would bloat and slow down every install). Instead this
checks whether Chromium is already there and, if not, downloads it in the
background exactly like `playwright install chromium` would.

Invokes Playwright's own driver executable directly (the same call
`python -m playwright` makes internally — see playwright/__main__.py)
rather than `sys.executable -m playwright`: inside a PyInstaller-frozen
app, sys.executable is the frozen .exe itself, not a Python interpreter,
so `-m` dispatch doesn't work there. Resolving the driver via Playwright's
own package path works identically in a dev venv and in the frozen app, as
long as the PyInstaller build includes playwright's `driver/` folder as
data (see packaging/jobsprint.spec).
"""

import os
import subprocess
import sys
import threading


def _chromium_executable_path():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        return p.chromium.executable_path


def is_chromium_installed() -> bool:
    try:
        return os.path.exists(_chromium_executable_path())
    except Exception:
        return False


class BrowserSetup:
    """`is_ready()` gates /api/session/start so a session can't try to
    launch a browser that's still being downloaded."""

    def __init__(self, event_bus):
        self.event_bus = event_bus
        self._ready = threading.Event()
        if is_chromium_installed():
            self._ready.set()

    def is_ready(self) -> bool:
        return self._ready.is_set()

    def ensure_installed_async(self):
        """Non-blocking — kicks off the download on a background thread if needed."""
        if self._ready.is_set():
            return
        threading.Thread(target=self._install, daemon=True).start()

    def _install(self):
        self.event_bus.publish(
            "activity_update", text="Setting up browser (one-time, needs internet)…"
        )
        self.event_bus.publish(
            "log_line", text="Downloading Chromium for Playwright — this only happens once."
        )
        try:
            from playwright._impl._driver import compute_driver_executable, get_driver_env

            driver_executable, driver_cli = compute_driver_executable()
            kwargs = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

            proc = subprocess.Popen(
                [driver_executable, driver_cli, "install", "chromium"],
                env=get_driver_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, **kwargs,
            )
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.event_bus.publish("log_line", text=line)
            proc.wait()

            if proc.returncode == 0 and is_chromium_installed():
                self._ready.set()
                self.event_bus.publish("activity_update", text="Browser ready.")
            else:
                self.event_bus.publish(
                    "activity_update",
                    text="Browser setup failed — check your internet connection and restart the app.",
                )
        except Exception as e:
            self.event_bus.publish("activity_update", text=f"Browser setup failed: {e}")
