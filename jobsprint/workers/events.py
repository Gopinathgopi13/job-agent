"""Thread-safe event bus bridging the synchronous Playwright worker thread
and the asyncio FastAPI/WebSocket layer.

Worker threads (fully synchronous, blocking Playwright code) call publish()
directly — cheap, non-blocking, no asyncio objects touched. The FastAPI side
drains events with a blocking get() from inside `run_in_executor` and
broadcasts them to connected WebSocket clients. See jobsprint/dashboard/routes_ws.py.

publish() also fans out synchronously to any registered listeners (e.g.
SessionOrchestrator's StatsStore) *in addition to* enqueueing for the
WebSocket drain — this keeps stats aggregation (needed for GET /api/stats
on page load/reconnect) independent of whether anything is currently
draining the queue, without turning this into a multi-consumer queue.
Listener callbacks run on the calling (worker) thread, so they must be fast
and non-blocking — just updating an in-memory dict under a lock.
"""

import queue
import time
from dataclasses import dataclass, field


@dataclass
class Event:
    type: str
    data: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def to_json(self):
        return {"type": self.type, "data": self.data, "ts": self.ts}


class EventBus:
    def __init__(self):
        self._queue = queue.Queue()
        self._listeners = []

    def subscribe(self, callback):
        """callback(event: Event) -> None, invoked synchronously on publish()."""
        self._listeners.append(callback)

    def publish(self, event_type: str, **data):
        event = Event(type=event_type, data=data)
        self._queue.put(event)
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass  # a broken listener must never take down the worker thread

    def get(self, timeout=None):
        """Blocking get. Call from a background thread, or from asyncio via
        `loop.run_in_executor(None, bus.get)`. Returns None on timeout."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None
