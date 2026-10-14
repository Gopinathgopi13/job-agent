"""Job-search preferences. Deliberately NOT scoped per Naukri login — this
is a single-user local desktop app, and "which role/location to search" is a
property of the installation, not of whichever Naukri account happens to be
logged into a given session. Lives at jobsprint/paths.py:PREFS_PATH.
"""

import json
import os
import threading

from .. import paths

DEFAULTS = {
    "role": "",
    "location": "",
    "experience": 3,
    "job_age_days": 3,
    "jobs_target": 10,
    "question_timeout_minutes": 30,
    "auto_apply_external": False,
}

# Keys written by older versions, dropped in the move to a single role and a
# single experience value. Migrated on read so an existing preferences.json
# keeps working instead of silently reintroducing removed behaviour.
_RETIRED_KEYS = ("roles", "experience_range", "min_match_score")


def _migrate(raw: dict) -> dict:
    """Fold any legacy keys into their modern equivalents, then drop them."""
    migrated = dict(raw)

    if "role" not in migrated and migrated.get("roles"):
        first = next((r for r in migrated["roles"] if r), None)
        if first:
            migrated["role"] = first

    if "experience" not in migrated and migrated.get("experience_range"):
        # "1to5" / "1-5" → take the lower bound; a bare number stays as-is.
        digits = "".join(c if c.isdigit() else " " for c in str(migrated["experience_range"])).split()
        if digits:
            migrated["experience"] = int(digits[0])

    for key in _RETIRED_KEYS:
        migrated.pop(key, None)
    return migrated


class PreferencesStore:
    def __init__(self, path: str = None):
        self.path = path or paths.PREFS_PATH
        self._lock = threading.Lock()

    def exists(self) -> bool:
        """False until the first successful save — the signal for whether
        there's a real prior role/target worth showing back as a default,
        as opposed to just the generic DEFAULTS fallback."""
        return os.path.exists(self.path)

    def _read_unlocked(self) -> dict:
        merged = dict(DEFAULTS)
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                merged.update(_migrate(json.load(f)))
        return merged

    def load(self) -> dict:
        with self._lock:
            return self._read_unlocked()

    def save(self, updates: dict) -> dict:
        with self._lock:
            merged = self._read_unlocked()
            merged.update({
                k: v for k, v in updates.items()
                if v is not None and k not in _RETIRED_KEYS
            })
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=4)
            return merged
