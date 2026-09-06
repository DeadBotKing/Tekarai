"""Framework-free feedback vocabularies and signal math for Phase 13-V.

Feedback is the only signal in the platform that comes from a human, so
this module's job is to make it *comparable*: a rating, a thumb, a
correction and a flag all become one normalized record with one sentiment
and one weight, and a stream of them becomes a score a dashboard or a
quality gate can act on.

Contents:

- ``FEEDBACK_KINDS`` — how the human expressed themselves (§33);
- ``FEEDBACK_REASONS`` — *why* an answer was bad, which is what makes
  feedback actionable rather than merely negative;
- ``FEEDBACK_STATUSES`` — the triage lifecycle from raw signal to a
  promoted golden case;
- ``FeedbackPolicy`` — when a complaint becomes a Phase 13-U case;
- normalization and aggregation math (rating → sentiment, satisfaction,
  net sentiment, reason ranking).

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
Sentiment keeps using the Phase 13-B ``FEEDBACK_SENTIMENTS`` vocabulary.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from apps.ai.domain.valueObjects.aiTypes import FEEDBACK_SENTIMENTS, ensureEnum
from apps.sharedKernel.domain.errors import ValidationFailedError

#: How the human expressed the feedback (§33).
FEEDBACK_KINDS = ("RATING", "THUMBS", "CORRECTION", "FLAG", "COMMENT")

#: Why an answer was unsatisfactory. A negative signal without a reason is
#: a complaint; with a reason it is a work item (§V.5).
FEEDBACK_REASONS = (
    "INACCURATE",
    "INCOMPLETE",
    "UNGROUNDED",
    "UNSAFE",
    "OFF_TOPIC",
    "TOO_SLOW",
    "TOO_VERBOSE",
    "FORMATTING",
    "OTHER",
)

#: Triage lifecycle: raw signal → reviewed → promoted into an evaluation case.
FEEDBACK_STATUSES = ("NEW", "TRIAGED", "ACCEPTED", "REJECTED", "PROMOTED")
TERMINAL_FEEDBACK_STATUSES = ("REJECTED", "PROMOTED")

#: Reasons that map onto a Phase 13-U metric, so a promoted case is graded
#: on the very thing the human complained about.
REASON_TO_METRIC = {
    "INACCURATE": "COMPLETENESS",
    "INCOMPLETE": "COMPLETENESS",
    "UNGROUNDED": "GROUNDEDNESS",
    "UNSAFE": "SAFETY",
    "OFF_TOPIC": "RELEVANCE",
    "TOO_SLOW": "LATENCY",
    "TOO_VERBOSE": "RELEVANCE",
    "FORMATTING": "SCHEMA_VALIDITY",
}

#: Absolute guards independent of configuration (§V.12).
MIN_RATING = 1
MAX_RATING = 5
MAX_COMMENT_LENGTH = 4000
MAX_CORRECTION_LENGTH = 8000
SCORE_PRECISION = 6


def ensureFeedbackEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown feedback vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureFeedbackKind(value: str) -> str:
    return ensureFeedbackEnum(value, FEEDBACK_KINDS, "kind")


def ensureFeedbackReason(value: str) -> str:
    return ensureFeedbackEnum(value, FEEDBACK_REASONS, "reason")


def ensureFeedbackStatus(value: str) -> str:
    return ensureFeedbackEnum(value, FEEDBACK_STATUSES, "status")


def ensureSentiment(value: str) -> str:
    return ensureEnum(value, FEEDBACK_SENTIMENTS, "feedbackSentiment")


def normalizeRating(value: int | None) -> int | None:
    """Validate a 1–5 rating, or ``None`` when the kind carries no rating."""

    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValidationFailedError("Feedback rating must be an integer.")
    if not MIN_RATING <= value <= MAX_RATING:
        raise ValidationFailedError(
            "Feedback rating must be between one and five.",
            fieldErrors={"rating": str(value)},
        )
    return value


def sentimentForRating(rating: int | None) -> str:
    """Map a 1–5 rating onto the Phase 13-B sentiment vocabulary.

    Four and five are positive, three is neutral, one and two are
    negative. Stated once here so no caller invents its own cut-off.
    """

    if rating is None:
        return "NEUTRAL"
    normalized = normalizeRating(rating)
    assert normalized is not None
    if normalized >= 4:
        return "POSITIVE"
    if normalized <= 2:
        return "NEGATIVE"
    return "NEUTRAL"


def sentimentWeight(sentiment: str) -> float:
    """Numeric weight used by net-sentiment aggregation."""

    chosen = ensureSentiment(sentiment)
    return {"POSITIVE": 1.0, "NEUTRAL": 0.0, "NEGATIVE": -1.0}[chosen]


def feedbackFingerprint(
    requestId: object, userId: object, kind: str, *, responseId: object = None
) -> str:
    """Idempotency key: one signal of one kind per user per response.

    Re-submitting the same thumb must not inflate the numbers; changing
    one's mind is an *update* of the same slot, not a second vote.
    """

    parts = (
        str(requestId or ""),
        str(responseId or ""),
        str(userId or "anonymous"),
        ensureFeedbackKind(kind),
    )
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def satisfactionScore(ratings: Iterable[int]) -> float:
    """Mean rating rescaled into ``[0, 1]`` (1 → 0.0, 5 → 1.0)."""

    values = [normalizeRating(rating) for rating in ratings]
    concrete = [value for value in values if value is not None]
    if not concrete:
        return 0.0
    mean = sum(concrete) / len(concrete)
    return round((mean - MIN_RATING) / (MAX_RATING - MIN_RATING), SCORE_PRECISION)


def netSentiment(sentiments: Iterable[str]) -> float:
    """Average sentiment weight in ``[-1, 1]``; empty input is neutral."""

    weights = [sentimentWeight(value) for value in sentiments]
    if not weights:
        return 0.0
    return round(sum(weights) / len(weights), SCORE_PRECISION)


def rankReasons(reasons: Iterable[str]) -> tuple[tuple[str, int], ...]:
    """Reason counts, most frequent first, ties broken alphabetically."""

    counts: dict[str, int] = {}
    for reason in reasons:
        if not reason:
            continue
        normalized = ensureFeedbackReason(reason)
        counts[normalized] = counts.get(normalized, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def metricForReason(reason: str) -> str:
    """The Phase 13-U metric a reason maps onto (``""`` when unmapped)."""

    return REASON_TO_METRIC.get(ensureFeedbackReason(reason), "")


@dataclass(frozen=True)
class FeedbackPolicy:
    """When a complaint becomes a golden case (§V.8)."""

    promotionThreshold: int = 2
    requireCorrection: bool = True
    requireReason: bool = True
    negativeRatingCeiling: int = 2
    minimumSatisfaction: float = 0.6
    trendTolerance: float = 0.05

    def __post_init__(self) -> None:
        if self.promotionThreshold < 1:
            raise ValidationFailedError("promotionThreshold must be positive.")
        normalized = normalizeRating(self.negativeRatingCeiling)
        if normalized is None:
            raise ValidationFailedError("negativeRatingCeiling is required.")
        for name in ("minimumSatisfaction", "trendTolerance"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValidationFailedError(
                    f"{name} must lie in [0, 1].", fieldErrors={name: str(value)}
                )
        for name in ("requireCorrection", "requireReason"):
            if not isinstance(getattr(self, name), bool):
                raise ValidationFailedError(f"{name} must be boolean.")

    def isNegativeRating(self, rating: int | None) -> bool:
        return rating is not None and rating <= self.negativeRatingCeiling

    def signature(self) -> str:
        return (
            f"{self.promotionThreshold}|{int(self.requireCorrection)}"
            f"|{int(self.requireReason)}|{self.negativeRatingCeiling}"
            f"|{self.minimumSatisfaction}"
        )


def coherentSentiment(kind: str, rating: int | None, sentiment: str = "") -> str:
    """Derive the sentiment a signal really carries.

    An explicit sentiment wins; otherwise a rating decides; otherwise the
    kind does (a ``FLAG`` is negative by definition, a bare ``COMMENT``
    is neutral until a human says otherwise).
    """

    chosenKind = ensureFeedbackKind(kind)
    if sentiment:
        return ensureSentiment(sentiment)
    if rating is not None:
        return sentimentForRating(rating)
    if chosenKind == "FLAG":
        return "NEGATIVE"
    if chosenKind == "CORRECTION":
        return "NEGATIVE"
    return "NEUTRAL"


def summarizeWeights(counts: Mapping[str, int]) -> float:
    """Net sentiment from pre-aggregated counts (used by read models)."""

    total = sum(int(value) for value in counts.values())
    if total <= 0:
        return 0.0
    weighted = sum(sentimentWeight(key) * int(value) for key, value in counts.items())
    return round(weighted / total, SCORE_PRECISION)


def clampText(value: str, limit: int, fieldName: str) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise ValidationFailedError(
            f"Feedback {fieldName} is too long.", fieldErrors={fieldName: str(len(text))}
        )
    return text


__all__ = [
    "FEEDBACK_KINDS",
    "FEEDBACK_REASONS",
    "FEEDBACK_STATUSES",
    "MAX_COMMENT_LENGTH",
    "MAX_CORRECTION_LENGTH",
    "MAX_RATING",
    "MIN_RATING",
    "REASON_TO_METRIC",
    "SCORE_PRECISION",
    "TERMINAL_FEEDBACK_STATUSES",
    "FeedbackPolicy",
    "clampText",
    "coherentSentiment",
    "ensureFeedbackEnum",
    "ensureFeedbackKind",
    "ensureFeedbackReason",
    "ensureFeedbackStatus",
    "ensureSentiment",
    "feedbackFingerprint",
    "metricForReason",
    "netSentiment",
    "normalizeRating",
    "rankReasons",
    "satisfactionScore",
    "sentimentForRating",
    "sentimentWeight",
    "summarizeWeights",
]
