"""Feedback port interfaces for Phase 13-V.

Minimal contracts the application layer depends on:

- ``FeedbackStore`` — persistence of signals, including the fingerprint
  lookup that makes submission idempotent;
- ``GoldenCasePublisher`` — the Phase 13-U surface used to register a
  promoted complaint as an evaluation case. The signature matches
  ``EvaluationApplicationService.registerCase`` exactly, so the real
  service satisfies it structurally and V imports nothing from U;
- ``FeedbackAuditLogger`` — the single Phase 13-O ledger append.

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from apps.ai.domain.entities.feedbackRecords import AIFeedbackEntry


class FeedbackStore(Protocol):
    """Persistence contract for human feedback signals."""

    def saveEntry(self, entry: AIFeedbackEntry) -> AIFeedbackEntry: ...
    def updateEntry(self, entry: AIFeedbackEntry) -> AIFeedbackEntry: ...
    def getEntry(self, tenantId: UUID, feedbackId: UUID) -> AIFeedbackEntry | None: ...
    def findByFingerprint(self, tenantId: UUID, fingerprint: str) -> AIFeedbackEntry | None: ...
    def listEntries(
        self,
        tenantId: UUID,
        *,
        statuses: tuple[str, ...] = (),
        sentiments: tuple[str, ...] = (),
        requestId: UUID | None = None,
        modelCode: str = "",
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 500,
    ) -> tuple[AIFeedbackEntry, ...]: ...
    def countByStatus(self, tenantId: UUID) -> dict[str, int]: ...
    def deleteEntriesBefore(self, tenantId: UUID | None, cutoff: datetime) -> int: ...


class GoldenCasePublisher(Protocol):
    """Phase 13-U: register a promoted complaint as an evaluation case."""

    def registerCase(self, tenantId: Any, command: Any) -> Any: ...


class FeedbackAuditLogger(Protocol):
    """The single Phase 13-O entry point V needs (one ledger append)."""

    def logAudit(
        self,
        tenantId: Any,
        action: str,
        *,
        outcome: str = ...,
        actorId: Any = ...,
        contextSources: tuple[str, ...] | list[str] | None = ...,
        detail: dict[str, Any] | None = ...,
    ) -> Any: ...


__all__ = [
    "FeedbackAuditLogger",
    "FeedbackStore",
    "GoldenCasePublisher",
]
