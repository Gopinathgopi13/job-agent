"""Deterministic, explainable question matching against the knowledge base.

Replaces the old TensorFlow bag-of-words classifier, which always emitted
a top class with no calibrated "I don't know" signal. rapidfuzz gives an
explicit similarity score we can threshold on, so "never guess" becomes a
simple, inspectable rule instead of something baked into opaque weights.
"""

import re
import string
from dataclasses import dataclass, field
from typing import Optional

from rapidfuzz import fuzz

from . import resolver

AUTO = "auto"
CONFIRM = "confirm"
ASK = "ask"

AUTO_THRESHOLD = 90
CONFIRM_THRESHOLD = 70
PASSIVE_LEARN_CEILING = 97  # AUTO matches below this silently add the phrasing as a variant

_PUNCT_TABLE = str.maketrans("", "", string.punctuation)

# Question-frame filler words. Two unrelated questions phrased the same way
# ("What is your X?" / "What is your Y?") share these tokens, which inflates
# rapidfuzz's token_set_ratio and can push a completely unrelated question
# into the CONFIRM band. Stripping them before scoring makes the match
# driven by actual content words instead of sentence shape.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "do", "does", "did",
    "you", "your", "yours", "i", "me", "my", "we", "our", "us", "to",
    "of", "for", "in", "on", "at", "and", "or", "please", "tell",
    "can", "could", "would", "will", "have", "has", "had", "be", "this",
    "that", "it", "with", "about", "as",
}


def normalize(text: str) -> str:
    text = text.lower().translate(_PUNCT_TABLE)
    return re.sub(r"\s+", " ", text).strip()


def _score_text(text: str) -> str:
    """Normalized text with question-frame stopwords stripped, for scoring only."""
    words = [w for w in normalize(text).split() if w not in _STOPWORDS]
    return " ".join(words) if words else normalize(text)


@dataclass
class MatchResult:
    decision: str
    question: str
    entry: Optional[dict] = None
    answer: Optional[str] = None
    score: float = 0.0
    candidates: list = field(default_factory=list)  # [{entry_id, tag, canonical_question, answer}]


class KBMatcher:
    def __init__(self, store, profile: dict):
        self.store = store
        self.profile = profile

    def refresh_profile(self, profile: dict):
        self.profile = profile

    def match(self, question: str) -> MatchResult:
        corpus = self.store.get_corpus()
        if not corpus:
            return MatchResult(decision=ASK, question=question)

        norm_q = _score_text(question)
        texts = [_score_text(t) for _, t in corpus]

        # token_set_ratio stays the score the thresholds are read against, but
        # on its own it can't separate a specific phrasing from a short generic
        # one: it returns a flat 100 whenever one side's tokens are a *subset*
        # of the other's. "Are you willing to relocate?" is a subset of "select
        # the city you are residing in or willing to relocate to", so the
        # yes/no intent tied with the city-picker intent and won on seed order
        # — answering a "which city?" question with "Yes".
        #
        # token_sort_ratio does notice the length/content gap (100 vs 51 for
        # that pair), so it breaks ties. Ranking on the pair keeps every
        # existing AUTO/CONFIRM decision exactly where it was while sending
        # ties to the more specific phrasing.
        best_by_entry = {}
        for idx, text in enumerate(texts):
            key = (fuzz.token_set_ratio(norm_q, text), fuzz.token_sort_ratio(norm_q, text))
            entry_id = corpus[idx][0]
            if entry_id not in best_by_entry or key > best_by_entry[entry_id]:
                best_by_entry[entry_id] = key

        ranked = sorted(best_by_entry.items(), key=lambda kv: kv[1], reverse=True)
        if not ranked:
            return MatchResult(decision=ASK, question=question)

        top_entry_id, (top_score, _tiebreak) = ranked[0]
        top_entry = self.store.get_entry(top_entry_id)

        candidates = []
        for entry_id, (score, _) in ranked[:3]:
            e = self.store.get_entry(entry_id)
            if e:
                candidates.append({
                    "entry_id": e["id"], "tag": e["tag"],
                    "canonical_question": e["canonical_question"],
                    "answer": resolver.resolve(e, self.profile),
                    "score": score,
                })

        if top_score >= AUTO_THRESHOLD:
            answer = resolver.resolve(top_entry, self.profile)
            if not str(answer).strip():
                # Confident about *which* question this is, but the profile
                # field behind it is empty. Submitting a blank is worse than
                # asking once and remembering the answer.
                return MatchResult(
                    decision=ASK, question=question, entry=top_entry,
                    answer=None, score=top_score, candidates=candidates,
                )
            if top_score < PASSIVE_LEARN_CEILING:
                self.store.add_variant(top_entry_id, question)
            self.store.touch_usage(top_entry_id)
            return MatchResult(
                decision=AUTO, question=question, entry=top_entry,
                answer=answer, score=top_score, candidates=candidates,
            )

        if top_score >= CONFIRM_THRESHOLD:
            answer = resolver.resolve(top_entry, self.profile)
            return MatchResult(
                decision=CONFIRM, question=question, entry=top_entry,
                answer=answer or None, score=top_score, candidates=candidates,
            )

        return MatchResult(decision=ASK, question=question, score=top_score, candidates=candidates)

    # ── feedback ───────────────────────────────────────────────

    def accept_confirm(self, result: MatchResult):
        """User accepted the suggested answer for a CONFIRM decision."""
        self.store.add_variant(result.entry["id"], result.question)
        self.store.touch_usage(result.entry["id"])

    def teach(self, question: str, answer: str) -> dict:
        """User typed a fresh answer (ASK, or a rejected CONFIRM)."""
        entry = self.store.create_user_taught(question, answer)
        return entry
