"""The pause/resume primitive.

The Playwright worker thread (still fully synchronous — see
ChatbotAgent._resolve_question in jobsprint/automation/naukri.py) calls submit() and
blocks on a plain threading.Event. The FastAPI/UI side calls resolve() or
cancel() once the user answers (or the request times out), which wakes the
worker back up. Nothing here touches asyncio — the bridge to WebSocket
notifications is EventBus (jobsprint/workers/events.py), which is safe to publish
into from any thread.
"""

import threading
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class PendingQuestion:
    id: str
    question: str
    candidates: list
    suggested_answer: str
    job_ctx: dict
    event: threading.Event
    options: list = None
    answer: str = None
    cancelled: bool = False
    created_at: float = field(default_factory=time.time)


class PendingQuestionRegistry:
    DEFAULT_TIMEOUT_SECONDS = 30 * 60

    def __init__(self, event_bus=None, default_timeout=None):
        self._lock = threading.Lock()
        self._pending = {}
        self.event_bus = event_bus
        self.default_timeout = default_timeout or self.DEFAULT_TIMEOUT_SECONDS

    def submit(self, question, candidates=None, suggested_answer=None, job_ctx=None,
               timeout=None, options=None):
        """Blocks the calling (worker) thread until answered, cancelled, or timed out.
        Returns the answer string, or None if the job must be skipped."""
        pq = PendingQuestion(
            id=str(uuid.uuid4()), question=question, candidates=candidates or [],
            suggested_answer=suggested_answer, job_ctx=job_ctx or {},
            event=threading.Event(), options=options or [],
        )
        with self._lock:
            self._pending[pq.id] = pq

        if self.event_bus:
            self.event_bus.publish(
                "question_pending", id=pq.id, question=question,
                candidates=candidates or [], suggested_answer=suggested_answer,
                job=job_ctx or {}, options=options or [],
            )

        resolved_in_time = pq.event.wait(timeout or self.default_timeout)

        with self._lock:
            self._pending.pop(pq.id, None)

        if not resolved_in_time or pq.cancelled:
            status = "cancelled" if pq.cancelled else "timeout"
            if self.event_bus:
                self.event_bus.publish("question_resolved", id=pq.id, status=status)
            return None

        if self.event_bus:
            self.event_bus.publish("question_resolved", id=pq.id, status="answered")
        return pq.answer

    def resolve(self, question_id: str, answer: str) -> bool:
        with self._lock:
            pq = self._pending.get(question_id)
            if not pq:
                return False
            pq.answer = answer
            pq.event.set()
        return True

    def cancel(self, question_id: str) -> bool:
        with self._lock:
            pq = self._pending.get(question_id)
            if not pq:
                return False
            pq.cancelled = True
            pq.event.set()
        return True

    def list_pending(self):
        with self._lock:
            return [
                {
                    "id": pq.id, "question": pq.question, "candidates": pq.candidates,
                    "suggested_answer": pq.suggested_answer, "job": pq.job_ctx,
                    "created_at": pq.created_at,
                }
                for pq in self._pending.values()
            ]
