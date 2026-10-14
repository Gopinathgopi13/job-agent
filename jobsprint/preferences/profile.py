"""The user's personal/career profile — the ground-truth source for KB answers
(jobsprint/knowledge/resolver.py reads this live, never a cached copy).

Three layers, each overriding the one before:

    1. DEFAULT_PROFILE   built-in fallbacks, so nothing is ever missing
    2. config.json       the editable file in the repo root — this is what
                         someone cloning the project fills in
    3. profile.json      per-machine, written by the dashboard's Profile tab,
                         and never committed anywhere

Layering this way means a public checkout is configured by editing one
tracked file, while anything you set through the dashboard stays local and
still wins.
"""

import json
import os
import threading

from .. import paths

DEFAULT_PROFILE = {
    "Salutation": "",
    "Full name": "",
    "First name": "",
    "Last name": "",
    "Location": "",
    "Current location": "",
    "Total experience": "5",
    "Current CTC": "9 LPA",
    "Expected salary": "15 LPA",
    "Salary": "9 LPA",
    "Mobile": "",
    "Email": "",
    "Notice period": "15",
    "Notice period negotiable": "Yes",
    "Date of birth": "",
    "Gender": "",
    "Father's name": "",
    "Mother's name": "",
    "Marital status": "",
    "Preferred work location": "",
    "Relocate": "Yes",
    "Open to relocate": "Yes",
    "Immediately available": "Yes",
    "Highest qualification": "",
    "Passport": "Yes",
    "Shift willingness": "Yes",
    "Vehicle": "Yes",
    "Work authorization": "Yes",
    "Visa sponsorship required": "No",
    "Resume path": "",
    "Cover letter": "",
    "Skills": {},
}

# Repo-root config.json, four levels up from this module.
CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config.json",
)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    # Keys used purely as file comments, and blanks left in the template, must
    # not overwrite a real value coming from a lower layer.
    return {
        k: v for k, v in data.items()
        if not k.startswith("__") and v not in ("", None, {})
    }


def load_config_defaults():
    """The editable config.json layer (empty dict if absent or malformed)."""
    return _read_json(CONFIG_PATH)


def job_roles(profile) -> list:
    """The 'Job roles' list from config.json, cleaned up. A single string is
    accepted too, and may be comma-separated."""
    raw = (profile or {}).get("Job roles") or []
    if isinstance(raw, str):
        raw = raw.split(",")
    seen, roles = set(), []
    for r in raw:
        r = str(r).strip()
        if r and r.lower() not in seen:
            seen.add(r.lower())
            roles.append(r)
    return roles


class ProfileStore:
    def __init__(self, path: str = None):
        self.path = path or paths.PROFILE_PATH
        self._lock = threading.Lock()

    def exists(self) -> bool:
        return os.path.exists(self.path)

    def _merged_unlocked(self) -> dict:
        merged = dict(DEFAULT_PROFILE)
        merged.update(load_config_defaults())
        merged.update(_read_json(self.path))
        return merged

    def load(self) -> dict:
        with self._lock:
            return self._merged_unlocked()

    def save(self, updates: dict) -> dict:
        with self._lock:
            merged = self._merged_unlocked()
            merged.update({k: v for k, v in updates.items() if v is not None})
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=4)
            return merged
