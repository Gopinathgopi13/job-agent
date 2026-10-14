"""Resume text extraction + skill extraction. pdfplumber is pure-Python
(via pdfminer.six) so it needs no native build step on Windows, and its
layout-aware extraction handles resume-style multi-column text better than
a bare pdfminer call.

This only feeds the job/resume match scorer — it never becomes a KB answer
source, so a bad extraction can't cause the bot to answer a question wrong.
"""

import os

import pdfplumber
from rapidfuzz import fuzz

from .skill_vocab import COMMON_TECH_SKILLS

FUZZY_MATCH_THRESHOLD = 85


def extract_text(path: str) -> str:
    parts = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)


def extract_skills(text: str, extra_vocab=None) -> list:
    vocab = list(dict.fromkeys(COMMON_TECH_SKILLS + list(extra_vocab or [])))
    text_lower = text.lower()
    found = []
    for term in vocab:
        term_lower = term.lower()
        if term_lower in text_lower or fuzz.partial_ratio(term_lower, text_lower) >= FUZZY_MATCH_THRESHOLD:
            found.append(term)
    return sorted(set(found))


def extract_skills_from_path(resume_path: str) -> list:
    """Best-effort — a missing/unreadable/non-PDF resume must never block a
    session from starting; callers just fall back to profile Skills alone."""
    if not resume_path or not resume_path.lower().endswith(".pdf") or not os.path.exists(resume_path):
        return []
    try:
        return extract_skills(extract_text(resume_path))
    except Exception:
        return []
