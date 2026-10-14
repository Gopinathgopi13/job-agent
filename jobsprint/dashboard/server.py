"""FastAPI app factory. Wraps a single in-process EventBus, SessionOrchestrator,
KBStore, ExcelTracker, PreferencesStore and ProfileStore — one of each, built
once at app startup (jobsprint/desktop.py) — so the Playwright worker thread and the
async HTTP/WebSocket layer share state safely.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..workers.events import EventBus

STATIC_DIR = Path(__file__).parent / "static"


def create_app(event_bus: EventBus, orchestrator=None, pending_registry=None,
                kb_store=None, tracker=None, prefs_store=None, profile_store=None,
                auth_token: str = None) -> FastAPI:
    from . import auth, routes_api, routes_ws

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = routes_ws.start_broadcaster(app)
        yield
        task.cancel()

    app = FastAPI(title="JobSprint", lifespan=lifespan)
    app.state.event_bus = event_bus
    app.state.orchestrator = orchestrator
    app.state.pending_registry = pending_registry
    app.state.kb_store = kb_store
    app.state.tracker = tracker
    app.state.prefs_store = prefs_store
    app.state.profile_store = profile_store
    # Always enforced — with no token passed in, a random one nobody knows
    # still keeps the API closed rather than open.
    app.state.auth_token = auth_token or auth.new_token()
    auth.install(app, app.state.auth_token)

    app.include_router(routes_ws.router)
    app.include_router(routes_api.router, prefix="/api")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(STATIC_DIR / "index.html"))

    return app
