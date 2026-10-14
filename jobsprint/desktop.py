"""Desktop launcher: runs the FastAPI backend in a background thread and
opens it in a native window via pywebview on the main thread (pywebview's
event loop must own the main thread on Windows).

Run with: python -m jobsprint.desktop
"""

import threading

import uvicorn
import webview

from . import paths
from .automation.browser import BrowserSetup
from .knowledge.store import KBStore
from .preferences.store import PreferencesStore
from .preferences.profile import ProfileStore
from .tracker.excel_writer import ExcelTracker
from .workers.events import EventBus
from .workers.orchestrator import SessionOrchestrator
from .workers.pending_question import PendingQuestionRegistry
from .dashboard.auth import new_token
from .dashboard.server import create_app

HOST = "127.0.0.1"
PORT = 8756


def _run_server(app):
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


def main():
    event_bus = EventBus()
    pending_registry = PendingQuestionRegistry(event_bus=event_bus)

    # One of each — single-user desktop app, single fixed app-data location
    # (jobsprint/paths.py). No more per-Naukri-login-email storage keying.
    profile_store = ProfileStore()
    prefs_store = PreferencesStore()
    kb_store = KBStore(paths.DB_PATH, profile_store.load())
    tracker = ExcelTracker(paths.EXCEL_PATH)

    browser_setup = BrowserSetup(event_bus)

    orchestrator = SessionOrchestrator(
        event_bus, pending_registry, kb_store=kb_store, tracker=tracker,
        prefs_store=prefs_store, profile_store=profile_store,
        browser_ready_check=browser_setup.is_ready,
    )
    token = new_token()
    app = create_app(
        event_bus, orchestrator=orchestrator, pending_registry=pending_registry,
        kb_store=kb_store, tracker=tracker, prefs_store=prefs_store, profile_store=profile_store,
        auth_token=token,
    )

    server_thread = threading.Thread(target=_run_server, args=(app,), daemon=True)
    server_thread.start()

    # Non-blocking — if Chromium's missing this starts downloading it in the
    # background; /api/session/start rejects attempts to apply until it's ready.
    browser_setup.ensure_installed_async()

    webview.create_window(
        "JobSprint", f"http://{HOST}:{PORT}/?token={token}",
        width=1320, height=840, min_size=(1040, 700),
    )
    webview.start()


if __name__ == "__main__":
    main()
