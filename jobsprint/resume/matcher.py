"""Explainable (non-ML) job/resume match scoring.

Deliberately simple and inspectable, in the same spirit as the KB matcher:
a weighted sum of three signals computed straight from the search-results
listing card (title, experience range, any visible skill tags) — no need
to open the full job page just to decide whether it's worth applying to,
which keeps a "scan 50 jobs, apply to the 10 good ones" session fast.
"""

import re

from rapidfuzz import fuzz

from .skill_vocab import COMMON_TECH_SKILLS

WEIGHT_SKILLS = 0.5
WEIGHT_EXPERIENCE = 0.3
WEIGHT_TITLE = 0.2


def parse_experience_range(text):
    """'2-5 yrs' / '3+ yrs' / '4 yrs' / '1to5' -> (min, max) or None."""
    if not text:
        return None
    t = str(text).lower().replace("yrs", "").replace("years", "").strip()
    m = re.search(r"(\d+)\s*(?:to|-)\s*(\d+)", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+)\s*\+", t)
    if m:
        lo = int(m.group(1))
        return lo, lo + 15
    m = re.search(r"(\d+)", t)
    if m:
        v = int(m.group(1))
        return v, v
    return None


MAX_EXPERIENCE_YEARS = 30  # Naukri's dropdown tops out here


def parse_experience_years(value):
    """A single number of years from whatever the caller had lying around.

    Accepts an int, "3", "3 years", or a legacy "1to5"/"1-5" range (older
    saved preferences used a range — take its lower bound so upgrading
    doesn't error). Returns None when there's nothing usable, meaning
    "don't apply an experience filter at all".
    """
    if value in (None, ""):
        return None
    m = re.search(r"\d+", str(value))
    if not m:
        return None
    return max(0, min(int(m.group()), MAX_EXPERIENCE_YEARS))


def parse_candidate_years(total_experience_field):
    """Best-effort int years from a profile field like '4' or '4 years'."""
    if total_experience_field in (None, ""):
        return None
    m = re.search(r"\d+", str(total_experience_field))
    return int(m.group()) if m else None


def _experience_fit(candidate_years, job_experience_text):
    rng = parse_experience_range(job_experience_text)
    if rng is None or candidate_years is None:
        return 0.7  # unknown on either side — neutral, don't hard-penalize
    lo, hi = rng
    if lo <= candidate_years <= hi:
        return 1.0
    distance = min(abs(candidate_years - lo), abs(candidate_years - hi))
    return max(0.0, 1.0 - distance / 5.0)


def _skill_overlap(required_skills, candidate_skills):
    if not required_skills:
        return 0.6  # nothing to compare against — neutral, not a rejection
    required_norm = {s.strip().lower() for s in required_skills if s and s.strip()}
    candidate_norm = {s.strip().lower() for s in candidate_skills if s and s.strip()}
    if not required_norm:
        return 0.6
    if not candidate_norm:
        return 0.0
    matched = sum(
        1 for req in required_norm
        if req in candidate_norm or any(fuzz.ratio(req, c) >= 90 for c in candidate_norm)
    )
    return matched / len(required_norm)


def _title_role_overlap(job_title, roles):
    if isinstance(roles, str):
        roles = [roles]
    roles = [r for r in (roles or []) if r]
    if not job_title or not roles:
        return 0.5
    title_norm = job_title.lower()
    return max((fuzz.token_set_ratio(role.lower(), title_norm) / 100.0 for role in roles), default=0.5)


def infer_required_skills(job_title, tags=None):
    """Listing cards don't always expose an explicit skills list — fall back
    to whichever known tech keywords literally appear in the title."""
    if tags:
        return list(tags)
    if not job_title:
        return []
    title_lower = job_title.lower()
    return [s for s in COMMON_TECH_SKILLS if s.lower() in title_lower]


def score_job(job: dict, candidate_skills, candidate_years, roles) -> float:
    """job: {'title': str, 'experience': str, 'tags': [str, ...]}. Returns 0-100."""
    required_skills = infer_required_skills(job.get("title"), job.get("tags"))

    skill_score = _skill_overlap(required_skills, candidate_skills)
    exp_score = _experience_fit(candidate_years, job.get("experience"))
    title_score = _title_role_overlap(job.get("title"), roles)

    weighted = skill_score * WEIGHT_SKILLS + exp_score * WEIGHT_EXPERIENCE + title_score * WEIGHT_TITLE
    return round(weighted * 100, 1)
