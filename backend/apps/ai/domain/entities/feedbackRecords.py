"""Feedback entities for Phase 13-V.

``AIFeedbackEntry`` is one human signal about one AI answer, carried all
the way from submission to the golden case it eventually becomes.

Per §33 a signal is attached to the *whole* provenance of the answer —
request, response, model, and prompt version — because "the summariser got
worse" is only actionable if you can tell which model and which prompt
version produced it.

The record also owns its triage lifecycle (``NEW → TRIAGED → ACCEPTED →
PROMOTED`` / ``REJECTED``), so feedback is not a write-only inbox: every
signal ends either as an evaluation case or as an explicit rejection with
a reason.

Pure dataclasses: no Django, ORM, HTTP, provider SDK, queue, or network
dependency. ``toDomainFeedback`` bridges to the Phase 13-B ``AIFeedback``
primitive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import AIFeedback, newId, requireUuid, utcNow
from apps.ai.domain.valueObjects.feedbackTypes import (
    MAX_COMMENT_LENGTH,
    MAX_CORRECTION_LENGTH,
    FeedbackPolicy,
    clampText,
    coherentSentiment,
    ensureFeedbackKind,
    ensureFeedbackReason,
    ensureFeedbackStatus,
    ensureSentiment,
    feedbackFingerprint,
    metricForReason,
    normalizeRating,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

#: Triage transitions (§V.6). ``PROMOTED`` and ``REJECTED`` are terminal.
#: Promotion implies acceptance: an automated sweep may take a qualifying
#: complaint straight from ``NEW`` to ``PROMOTED`` because the promotion
#: policy (``isPromotable``) is a stricter gate than manual triage. What is
#: never allowed is resurrecting a terminal signal.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "NEW": {"TRIAGED", "ACCEPTED", "REJECTED", "PROMOTED"},
    "TRIAGED": {"ACCEPTED", "REJECTED", "PROMOTED"},
    "ACCEPTED": {"PROMOTED", "REJECTED"},
    "REJECTED": set(),
    "PROMOTED": set(),
}

MAX_TARGET_LENGTH = 160


@dataclass
class AIFeedbackEntry:
    """One human signal about one AI answer (§V.4)."""

    tenantId: uuid.UUID
    requestId: uuid.UUID
    kind: str = "RATING"
    responseId: uuid.UUID | None = None
    userId: uuid.UUID | None = None
    rating: int | None = None
    sentiment: str = ""
    reason: str = ""
    comment: str = ""
    correction: str = ""
    question: str = ""
    modelCode: str = ""
    promptVersion: str = ""
    capabilityCode: str = ""
    suiteCode: str = ""
    status: str = "NEW"
    promotedCaseCode: str = ""
    rejectionReason: str = ""
    triagedBy: uuid.UUID | None = None
    triagedAt: datetime | None = None
    fingerprint: str = ""
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.id = requireUuid(self.id, "id")
        if self.responseId is not None:
            self.responseId = requireUuid(self.responseId, "responseId")
        if self.userId is not None:
            self.userId = requireUuid(self.userId, "userId")
        if self.triagedBy is not None:
            self.triagedBy = requireUuid(self.triagedBy, "triagedBy")
        self.kind = ensureFeedbackKind(self.kind)
        self.rating = normalizeRating(self.rating)
        self.sentiment = coherentSentiment(self.kind, self.rating, self.sentiment)
        self.reason = ensureFeedbackReason(self.reason) if self.reason else ""
        self.status = ensureFeedbackStatus(self.status)
        self.comment = clampText(self.comment, MAX_COMMENT_LENGTH, "comment")
        self.correction = clampText(self.correction, MAX_CORRECTION_LENGTH, "correction")
        self.question = clampText(self.question, MAX_CORRECTION_LENGTH, "question")
        for name in ("modelCode", "promptVersion", "capabilityCode", "suiteCode"):
            value = str(getattr(self, name) or "").strip()
            if len(value) > MAX_TARGET_LENGTH:
                raise ValidationFailedError(f"Feedback {name} is too long.")
            setattr(self, name, value.upper() if name != "promptVersion" else value)
        self.promotedCaseCode = str(self.promotedCaseCode or "").strip().upper()
        self.rejectionReason = clampText(self.rejectionReason, 500, "rejectionReason")
        if self.kind == "RATING" and self.rating is None:
            raise ValidationFailedError("A RATING signal requires a rating.")
        if self.kind == "CORRECTION" and not self.correction:
            raise ValidationFailedError("A CORRECTION signal requires correction text.")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Feedback metadata must be a mapping.")
        if not self.fingerprint:
            self.fingerprint = feedbackFingerprint(
                self.requestId, self.userId, self.kind, responseId=self.responseId
            )

    # -- reads ----------------------------------------------------------
    @property
    def isNegative(self) -> bool:
        return self.sentiment == "NEGATIVE"

    @property
    def isTerminal(self) -> bool:
        return self.status in ("PROMOTED", "REJECTED")

    @property
    def targetKey(self) -> str:
        """Grouping key for aggregation: model + prompt version (§33)."""

        model = self.modelCode or "UNKNOWN_MODEL"
        version = self.promptVersion or "-"
        return f"{model}@{version}"

    def suggestedMetric(self) -> str:
        return metricForReason(self.reason) if self.reason else ""

    def isPromotable(self, policy: FeedbackPolicy) -> bool:
        """Can this signal become a golden case on its own merits?"""

        if self.status not in ("ACCEPTED", "TRIAGED", "NEW"):
            return False
        if not self.isNegative:
            return False
        if not self.question:
            return False
        if policy.requireReason and not self.reason:
            return False
        if policy.requireCorrection and not self.correction:
            return False
        return True

    # -- lifecycle ------------------------------------------------------
    def transitionTo(self, status: str, *, now: datetime | None = None) -> None:
        target = ensureFeedbackStatus(status)
        if target != self.status and target not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValidationFailedError(
                f"Invalid feedback transition {self.status} → {target}.",
                fieldErrors={"status": target},
            )
        self.status = target
        self.updatedAt = now or utcNow()

    def accept(
        self, *, reviewerId: uuid.UUID | str | None = None, now: datetime | None = None
    ) -> None:
        moment = now or utcNow()
        self.transitionTo("ACCEPTED", now=moment)
        self.triagedBy = None if reviewerId is None else requireUuid(reviewerId, "reviewerId")
        self.triagedAt = moment

    def reject(
        self,
        reason: str,
        *,
        reviewerId: uuid.UUID | str | None = None,
        now: datetime | None = None,
    ) -> None:
        moment = now or utcNow()
        self.transitionTo("REJECTED", now=moment)
        self.rejectionReason = clampText(reason, 500, "rejectionReason")
        if not self.rejectionReason:
            raise ValidationFailedError("Rejecting feedback requires a reason.")
        self.triagedBy = None if reviewerId is None else requireUuid(reviewerId, "reviewerId")
        self.triagedAt = moment

    def promote(self, caseCode: str, *, suiteCode: str = "", now: datetime | None = None) -> None:
        code = str(caseCode or "").strip().upper()
        if not code:
            raise ValidationFailedError("Promotion requires a case code.")
        self.transitionTo("PROMOTED", now=now)
        self.promotedCaseCode = code
        if suiteCode:
            self.suiteCode = suiteCode.strip().upper()

    def revise(
        self,
        *,
        rating: int | None = None,
        sentiment: str = "",
        reason: str = "",
        comment: str = "",
        correction: str = "",
        now: datetime | None = None,
    ) -> None:
        """Apply a change of mind to the same slot (idempotency, §V.5).

        A terminal signal is frozen: once it became a case (or was
        rejected) rewriting it would silently rewrite history.
        """

        if self.isTerminal:
            raise ValidationFailedError("A promoted or rejected signal can no longer be revised.")
        if rating is not None:
            self.rating = normalizeRating(rating)
        if sentiment:
            self.sentiment = ensureSentiment(sentiment)
        elif rating is not None:
            self.sentiment = coherentSentiment(self.kind, self.rating, "")
        if reason:
            self.reason = ensureFeedbackReason(reason)
        if comment:
            self.comment = clampText(comment, MAX_COMMENT_LENGTH, "comment")
        if correction:
            self.correction = clampText(correction, MAX_CORRECTION_LENGTH, "correction")
        self.updatedAt = now or utcNow()

    # -- projections ----------------------------------------------------
    def toGoldenCaseDraft(self, *, suiteCode: str = "", caseCode: str = "") -> dict[str, Any]:
        """Shape used to register a Phase 13-U golden case.

        A plain mapping keeps the domain free of the evaluation service;
        the application layer turns it into a ``RegisterCaseCommand``.
        """

        if not self.question:
            raise ValidationFailedError(
                "Feedback without the original question cannot become a case."
            )
        expected = tuple(part for part in (self.correction.strip(),) if part)
        return {
            "suiteCode": (suiteCode or self.suiteCode or "FEEDBACK_GOLDEN").upper(),
            "caseCode": (caseCode or f"FEEDBACK_{str(self.id)[:8]}").upper(),
            "question": self.question,
            "expectedTerms": expected,
            "metadata": {
                "origin": "FEEDBACK",
                "feedbackId": str(self.id),
                "reason": self.reason,
                "metric": self.suggestedMetric(),
                "modelCode": self.modelCode,
                "promptVersion": self.promptVersion,
            },
        }

    def toDomainFeedback(self) -> AIFeedback:
        """Bridge to the Phase 13-B ``AIFeedback`` primitive."""

        if self.responseId is None:
            raise ValidationFailedError(
                "Feedback without responseId cannot be bridged to AIFeedback."
            )
        return AIFeedback(
            tenantId=self.tenantId,
            requestId=self.requestId,
            responseId=self.responseId,
            userId=self.userId,
            rating=self.rating,
            sentiment=self.sentiment,
            correction=self.correction,
            comment=self.comment,
            id=self.id,
            createdAt=self.createdAt,
        )


__all__ = [
    "MAX_TARGET_LENGTH",
    "AIFeedbackEntry",
]
