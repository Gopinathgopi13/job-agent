"""Shared helpers for the things you configure once in config.json — skip
lists and the application record format."""

import re
from datetime import datetime


def _squash(text):
    """Lowercase with spaces, hyphens and punctuation removed, so "Full
    Stack", "Full-Stack" and "Fullstack" all compare equal."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def skip_reason(user_info, url="", title="", company=""):
    """Why config.json's skip lists rule this job out, or None. Plain
    case-insensitive substring matching, so "Infosys" also catches
    "Infosys BPM" and "intern" catches "Internship". Spacing and punctuation
    are ignored too, so "Java Full Stack" also catches "Java Fullstack" and
    "Java Full-Stack"."""
    checks = [
        ("Skip companies", company, "company"),
        ("Skip title keywords", title, "title"),
        ("Skip job links", url, "link"),
    ]
    for field, value, what in checks:
        value = _squash(value)
        for term in user_info.get(field) or []:
            term = str(term).strip()
            if _squash(term) and _squash(term) in value:
                return f"{what} matches {term!r}"
    return None


def build_record(meta, job_url, application_type, status, external_url="", site=""):
    """One row of the session report / Excel tracker."""
    return {
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "site": site,
        "company": meta.get("company", ""), "job_role": meta.get("title", ""),
        "experience": meta.get("experience", ""), "salary": meta.get("salary", ""),
        "posted_date": meta.get("posted_date", ""), "naukri_url": job_url,
        "external_url": external_url, "application_type": application_type, "status": status,
    }
