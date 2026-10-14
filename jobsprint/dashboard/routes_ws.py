"""WebSocket endpoint + the bridge that drains the (thread-safe, sync)
EventBus and rebroadcasts each event to every connected browser tab.

The bridge runs as a normal asyncio task, but the actual wait for the next
event happens off the event loop (run_in_executor) since EventBus.get() is a
blocking queue.get() — this keeps the Playwright worker thread fully
decoupled from asyncio; it never touches an event loop or awaitable.
"""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .auth import websocket_allowed

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if not websocket_allowed(ws, ws.app.state.auth_token):
        await ws.close(code=1008)  # policy violation
        return
    await manager.connect(ws)
    try:
        while True:
            # Frontend doesn't need to send anything meaningful; this just
            # keeps the coroutine alive until the client disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


async def _broadcaster_loop(app):
    bus = app.state.event_bus
    loop = asyncio.get_event_loop()
    while True:
        event = await loop.run_in_executor(None, bus.get, 1.0)
        if event is not None:
            await manager.broadcast(event.to_json())


def start_broadcaster(app):
    return asyncio.create_task(_broadcaster_loop(app))
