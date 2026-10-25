"""The job boards a session can run against."""

from .hirist import HiristBot
from .naukri import NaukriBot

PORTALS = {
    "naukri": {
        "label": "Naukri",
        "bot": NaukriBot,
        "email_env": "NAUKRI_EMAILS",
    },
    "hirist": {
        "label": "Hirist",
        "bot": HiristBot,
        "email_env": "HIRIST_EMAILS",
    },
}


def normalize_portal(name):
    key = (name or "naukri").strip().lower()
    if key not in PORTALS:
        known = ", ".join(PORTALS)
        raise ValueError(f"Unknown portal {name!r}. Choose one of: {known}.")
    return key


def create_bot(portal, **kwargs):
    key = normalize_portal(portal)
    return PORTALS[key]["bot"](**kwargs)
