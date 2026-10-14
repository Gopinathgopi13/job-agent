"""Runs NaukriBot on a background thread and keeps an in-memory stats
snapshot in sync via EventBus listeners, so GET /api/stats always has an
authoritative answer (not just whatever the WebSocket happened to push).
"""

import threading

from ..automation.naukri import NaukriBot
from ..preferences import store as prefs_defaults
from ..preferences.profile import job_roles

_STAT_EVENT_DELTAS = {
    "job_scanned": {"jobs_scanned": 1},
    "job_matched": {"jobs_matched": 1},
    "application_submitted": {"applications_submitted": 1},
    "application_needs_input": {"applications_needing_input": 1},
    "external_application_collected": {"external_applications_collected": 1},
    "question_learned": {"questions_learned_total": 1},
}


class StatsStore:
    def __init__(self, event_bus):
        self._lock = threading.Lock()
        self._stats = {
            "jobs_scanned": 0,
            "jobs_matched": 0,
            "applications_submitted": 0,
            "applications_needing_input": 0,
            "external_applications_collected": 0,
            "questions_learned_total": 0,
            "current_activity": "Idle",
            "progress_percent": 0,
            "session_status": "idle",
        }
        self.event_bus = event_bus
        event_bus.subscribe(self._on_event)

    def _on_event(self, event):
        changed = False
        with self._lock:
            deltas = _STAT_EVENT_DELTAS.get(event.type)
            if deltas:
                for key, inc in deltas.items():
                    self._stats[key] += inc
                changed = True
            if event.type == "activity_update":
                self._stats["current_activity"] = event.data.get("text", "")
                changed = True
            if event.type == "progress_update":
                self._stats["progress_percent"] = event.data.get("percent", 0)
                changed = True
            if event.type == "session_status_changed":
                self._stats["session_status"] = event.data.get("status", "idle")
                changed = True
            snapshot = dict(self._stats)
        if changed:
            self.event_bus.publish("stats_update", **snapshot)

    def snapshot(self):
        with self._lock:
            return dict(self._stats)

    def reset_session_counters(self):
        with self._lock:
            for key in (
                "jobs_scanned", "jobs_matched", "applications_submitted",
                "applications_needing_input", "external_applications_collected",
                "questions_learned_total", "progress_percent",
            ):
                self._stats[key] = 0


class SessionOrchestrator:
    """kb_store/tracker/prefs_store/profile_store are each a single shared
    instance built once at app startup (jobsprint/desktop.py) — this is a single-user
    desktop app, so there's one knowledge base, one Excel tracker, one set
    of preferences, one profile, for the life of the process. Naukri login
    email/password are the only thing that's session-scoped."""

    def __init__(self, event_bus, pending_registry, kb_store, tracker,
                 prefs_store=None, profile_store=None, browser_ready_check=None):
        self.event_bus = event_bus
        self.pending_registry = pending_registry
        self.kb_store = kb_store
        self.tracker = tracker
        self.prefs_store = prefs_store
        self.profile_store = profile_store
        self.browser_ready_check = browser_ready_check
        self.stats = StatsStore(event_bus)
        self._lock = threading.Lock()
        self._thread = None
        self._bot = None
        self._stop_event = threading.Event()

    def get_stats(self):
        return self.stats.snapshot()

    def is_running(self):
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def start(self, email, password, username=None, jobs_target=None,
              role=None, location=None, experience=None, job_age=None):
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False, "A session is already running."

            if self.browser_ready_check is not None and not self.browser_ready_check():
                return False, "Still setting up the browser (one-time download) — try again shortly."

            self._stop_event = threading.Event()
            username = username or email

            prefs = self.prefs_store.load() if self.prefs_store else dict(prefs_defaults.DEFAULTS)
            jobs_target = jobs_target or prefs["jobs_target"]
            profile = self.profile_store.load() if self.profile_store else {}
            roles = [role] if role else (job_roles(profile) or [prefs["role"]])
            location = location or prefs["location"]
            experience = experience if experience is not None else prefs["experience"]
            job_age = job_age or prefs["job_age_days"]

            self.stats.reset_session_counters()

            from ..resume.parser import extract_skills_from_path
            resume_skills = extract_skills_from_path(profile.get("Resume path", ""))

            self._bot = NaukriBot(
                email=email, password=password, username=username, number=jobs_target,
                user_info=profile, pending_registry=self.pending_registry,
                event_bus=self.event_bus, on_application_recorded=self._handle_application_recorded,
                resume_skills=resume_skills,
            )
            self._bot.stop_event = self._stop_event

            self._thread = threading.Thread(
                target=self._run, args=(roles, experience, location, job_age), daemon=True,
            )
            self._thread.start()
            return True, "Session started."

    def stop(self):
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                return False, "No session is running."
            self._stop_event.set()
            self.event_bus.publish("activity_update", text="Stopping — finishing the current job…")
            return True, "Stop requested."

    def _handle_application_recorded(self, record: dict):
        """Called for every successfully-recorded application — both direct
        submissions and captured external links — so the Excel tracker and
        the `applications` SQLite table (used by the dashboard's history
        view) never fall out of sync with each other."""
        if self.tracker is not None:
            self.tracker.append_row(record)
        if self.kb_store is not None:
            self.kb_store.insert_application(record)
        if record.get("application_type") == "external":
            self.event_bus.publish("external_application_collected", **record)
        self.event_bus.publish("application_added", **record)

    def _run(self, roles, experience, location, job_age):
        bot = self._bot
        self.event_bus.publish("session_status_changed", status="running")
        self.event_bus.publish("activity_update", text="Launching browser and logging in…")
        try:
            bot.init_browser()
            if not bot.login():
                self.event_bus.publish("activity_update", text="Login failed.")
                self.event_bus.publish("session_status_changed", status="error")
                return

            result = {}
            for role in roles:
                if bot.applied_count >= bot.applno or bot.quota_exceeded or bot.stop_event.is_set():
                    break
                self.event_bus.publish("activity_update", text=f"Searching: {role}")
                result = bot.apply_for_role(role, experience, location, job_age)
            self.event_bus.publish(
                "activity_update",
                text=f"Session complete — applied {result.get('applied', 0)}, "
                     f"skipped {result.get('skipped', 0)}.",
            )
        except Exception as e:
            self.event_bus.publish("activity_update", text=f"Session error: {e}")
            self.event_bus.publish("session_status_changed", status="error")
            return
        finally:
            try:
                bot.shutdown()
            except Exception:
                pass
            if self.tracker is not None:
                try:
                    self.tracker.add_daily_summary(bot)
                except Exception as e:
                    self.event_bus.publish("activity_update", text=f"Couldn't update the Daily Summary sheet: {e}")
            with self._lock:
                self._thread = None
            self.event_bus.publish("session_status_changed", status="idle")
