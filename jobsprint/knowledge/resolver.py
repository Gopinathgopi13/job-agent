"""Resolves a kb_entries row to its current answer, live.

static_profile entries never trust a cached answer — they re-read the
user's profile every time, so editing the profile is always the single
source of truth (per the "never guess, profile is ground truth" requirement).
computed entries either run a small dynamic function (e.g. last working day)
or, if no function is registered for the tag, fall back to the literal
`answer` stored on the row (used for fixed constants like "Yes"/"No").
"""

from datetime import datetime, timedelta


def _resolve_profile_field(profile: dict, field: str):
    if not field:
        return None
    if "." in field:
        top, sub = field.split(".", 1)
        return (profile.get(top) or {}).get(sub)
    return profile.get(field)


def _compute_last_working_day(profile: dict) -> str:
    days = 30
    notice = profile.get("Notice period")
    try:
        days = int(str(notice).strip().split()[0])
    except (ValueError, IndexError, AttributeError):
        pass
    return (datetime.now() + timedelta(days=days)).strftime("%d/%m/%Y")


def _compute_fresher_or_exp(profile: dict) -> str:
    total = str(profile.get("Total experience", "0")).strip()
    return "Fresher" if total in ("", "0") else "Experienced"


def _compute_skills_summary(profile: dict) -> str:
    skills = profile.get("Skills") or {}
    return ", ".join(str(k) for k in skills.keys())


COMPUTE_REGISTRY = {
    "last_working_day": _compute_last_working_day,
    "fresher_or_exp": _compute_fresher_or_exp,
    "skills_summary": _compute_skills_summary,
}


def resolve(entry: dict, profile: dict) -> str:
    """entry is a kb_entries row (dict) as returned by KBStore."""
    source = entry.get("source")
    if source == "static_profile":
        field = entry.get("profile_field")
        value = _resolve_profile_field(profile, field)
        if (value is None or str(value).strip() == "") and str(field).startswith("Skills."):
            # A tool the profile doesn't list. Answering nothing here makes the
            # form pick whatever option scores least badly — usually "No
            # experience". Falling back to overall experience is both truthful
            # and keeps the application moving.
            value = profile.get("Total experience")
        return "" if value is None else str(value)
    if source == "computed":
        fn = COMPUTE_REGISTRY.get(entry["tag"])
        if fn:
            return fn(profile)
        return entry.get("answer") or ""
    # user_taught
    return entry.get("answer") or ""
