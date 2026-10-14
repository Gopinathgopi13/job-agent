"""Per-launch access token for the local dashboard.

The server only listens on 127.0.0.1, but that alone doesn't stop other
websites open in your normal browser from reaching it (cross-site requests,
WebSocket connections, DNS rebinding). So every launch generates a random
token; the desktop window opens `/?token=...`, which swaps it for an
HttpOnly, SameSite=Strict cookie. Every other request — REST, static files
and the WebSocket — must carry that cookie and a localhost Host header.
"""

import secrets

from fastapi import Request, WebSocket
from fastapi.responses import PlainTextResponse, RedirectResponse

COOKIE_NAME = "jobsprint_session"
_ALLOWED_HOSTNAMES = ("127.0.0.1", "localhost")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def _host_ok(host_header: str) -> bool:
    hostname = (host_header or "").rsplit(":", 1)[0]
    return hostname in _ALLOWED_HOSTNAMES


def _token_ok(expected: str, supplied: str) -> bool:
    return bool(supplied) and secrets.compare_digest(expected, supplied)


def install(app, token: str):
    """Attach the token check to every HTTP request on `app`."""

    @app.middleware("http")
    async def require_token(request: Request, call_next):
        if not _host_ok(request.headers.get("host")):
            return PlainTextResponse("Forbidden", status_code=403)

        # Launch URL: trade the one-time query token for a cookie, then drop
        # it from the address bar.
        if request.url.path == "/" and "token" in request.query_params:
            if not _token_ok(token, request.query_params["token"]):
                return PlainTextResponse("Forbidden", status_code=403)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie(
                COOKIE_NAME, token, httponly=True, samesite="strict", path="/",
            )
            return response

        if not _token_ok(token, request.cookies.get(COOKIE_NAME)):
            return PlainTextResponse("Forbidden", status_code=403)
        return await call_next(request)


def websocket_allowed(ws: WebSocket, token: str) -> bool:
    """HTTP middleware doesn't see WebSocket handshakes — check them here.
    Browsers always send Origin on a WebSocket handshake, so also require it
    to be this local server."""
    if not _host_ok(ws.headers.get("host")):
        return False
    origin = ws.headers.get("origin", "")
    origin_host = origin.split("://", 1)[-1]
    if not origin.startswith("http://") or not _host_ok(origin_host):
        return False
    return _token_ok(token, ws.cookies.get(COOKIE_NAME))
