"""Answering "how many years of experience do you have in <tool>?" for any
tool, without needing a knowledge-base entry per tool.

Application chatbots ask this about whatever happens to be in the job spec —
Kafka, OpenShift, Datadog, "AI, GenAI, LLM, RAG & Multi-agent". Seeding an
intent per tool is hopeless, and leaving it to fuzzy matching is worse than
it looks: "Experience in Golang" used to score 83% against whichever unrelated
skill entry happened to match and answer with *that* skill's number.

So this reads the tool straight out of the question, looks it up in the
profile's Skills map (fuzzily, so "Dockers" and "Teraform" still land), and
falls back to overall experience for anything not listed. Deterministic and
inspectable, same as the rest of the knowledge base — no guessing.

The answer is always the number of years, whatever shape the question takes.
That single value works against every kind of form control: a numeric option
list picks the right bucket, a Yes/No list coerces a positive number to "Yes"
(see ChatbotAgent._best_match), and a text box just receives the number.
"""

import re

from rapidfuzz import fuzz, process

# Question shapes that are asking about experience with a named thing. Ordered
# most-specific first; the capture group is the tool.
_PATTERNS = [
    r"(?:how\s+many\s+)?years?\s+of\s+experience\s+(?:do\s+you\s+have\s+)?(?:in|with|on|using)\s+(.+)",
    r"(?:total|relevant)\s+(?:years?\s+of\s+)?experience\s+(?:in|with|on)\s+(.+)",
    r"how\s+long\s+have\s+you\s+(?:been\s+)?work(?:ed|ing)?\s+(?:with|on|in|using)\s+(.+)",
    r"rate\s+your\s+(?:expertise|proficiency|skill|knowledge)\s+(?:in|with|on|of)\s+(.+)",
    r"do\s+you\s+have\s+(?:any\s+)?(?:hands[\s-]?on\s+)?(?:working\s+)?(?:experience|knowledge|exposure)\s+(?:in|with|of|on)\s+(.+)",
    r"experience\s+(?:in|with|on)\s+(.+)",
    r"(.+?)\s+experience\s+in\s+years",
    r"years?\s+of\s+(.+?)\s+experience",
]

# The question has to be about experience at all before any of the above are
# allowed to claim it — this keeps CTC/notice/location questions well clear.
_TOPIC = re.compile(
    r"experience|expertise|proficiency|worked|working|hands[\s-]?on|knowledge|exposure",
    re.I,
)

# Words that mean "the candidate overall", not a named technology.
_SELF_REFERENTIAL = {
    "", "it", "this", "that", "the above", "them", "these", "your current company",
    "your current role", "the above technologies", "total", "overall",
}

_SKILL_MATCH_THRESHOLD = 82  # "Dockers"->Docker ~92, "Teraform"->Terraform ~94


def _clean(fragment: str) -> str:
    fragment = fragment.strip().strip("?.!:,;").strip()
    fragment = re.sub(r"^(the|a|an)\s+", "", fragment, flags=re.I)
    fragment = re.sub(r"\s+(experience|skills?|tools?)$", "", fragment, flags=re.I)
    return fragment.strip()


def extract_topic(question: str):
    """The tool a question is asking about, '' when it's about overall
    experience, or None when it isn't an experience question at all."""
    if not question or not _TOPIC.search(question):
        return None

    text = " ".join(str(question).split())
    for pattern in _PATTERNS:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return _clean(match.group(1))

    # "How many years of experience do you have?" — no tool named.
    if re.search(r"years?\s+of\s+experience|total\s+experience", text, re.I):
        return ""
    return None


def lookup_years(topic: str, profile: dict):
    """Years for a named tool from the profile's Skills map, or None."""
    skills = profile.get("Skills") or {}
    if not topic or not skills:
        return None

    lowered = {str(name).strip().lower(): value for name, value in skills.items()}
    topic_lower = topic.lower()

    if topic_lower in lowered:
        return lowered[topic_lower]

    # A compound like "AI, GenAI, LLM, RAG & Multi-agent" — answer for any one
    # of the listed tools the profile actually knows.
    for part in re.split(r"[,/&]|\band\b", topic_lower):
        part = _clean(part).lower()
        if part and part in lowered:
            return lowered[part]

    best = process.extractOne(topic_lower, list(lowered), scorer=fuzz.ratio)
    if best and best[1] >= _SKILL_MATCH_THRESHOLD:
        return lowered[best[0]]
    return None


def answer_for(question: str, profile: dict):
    """The years to answer with, or None if this isn't an experience question.

    An unlisted tool falls back to overall experience rather than nothing —
    answering blank is what used to let forms settle on "No experience".
    """
    topic = extract_topic(question)
    if topic is None:
        return None

    if topic and topic.lower() in _SELF_REFERENTIAL:
        topic = ""

    years = lookup_years(topic, profile) if topic else None
    if years in (None, ""):
        years = profile.get("Total experience")

    return None if years in (None, "") else str(years)
