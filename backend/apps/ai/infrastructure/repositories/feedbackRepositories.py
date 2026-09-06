"""Django persistence for the Phase 13-V feedback platform.

Row↔entity mapping only — no business rule lives here. Every read and
write is tenant-scoped, and entities are rehydrated through the domain
record so an invalid stored row can never re-enter the domain.

``deleteEntriesBefore`` deliberately spares signals that are still in
flight: only ``PROMOTED`` and ``REJECTED`` rows are settled, and deleting
a complaint nobody has looked at yet would erase the very backlog triage
exists to work through.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db.models import Q

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.feedbackRecords import AIFeedbackEntry
from apps.ai.domain.exceptions import AIFeedbackInvalid
from apps.ai.domain.valueObjects.feedbackTypes import TERMINAL_FEEDBACK_STATUSES
from apps.ai.infrastructure.models import AIFeedbackEntryModel


def feedbackToEntity(row: AIFeedbackEntryModel) -> AIFeedbackEntry:
    """Map a feedback row to its domain record."""

    return AIFeedbackEntry(
        tenantId=row.tenantId,
        requestId=row.requestId,
        kind=row.kind,
        responseId=row.responseId,
        userId=row.userId,
        rating=row.rating,
        sentiment=row.sentiment,
        reason=row.reason or "",
        comment=row.comment or "",
        correction=row.correction or "",
        question=row.question or "",
        modelCode=row.modelCode or "",
        promptVersion=row.promptVersion or "",
        capabilityCode=row.capabilityCode or "",
        suiteCode=row.suiteCode or "",
        status=row.status,
        promotedCaseCode=row.promotedCaseCode or "",
        rejectionReason=row.rejectionReason or "",
        triagedBy=row.triagedBy,
        triagedAt=row.triagedAt,
        fingerprint=row.fingerprint,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
        updatedAt=row.updatedAt,
    )


class DjangoFeedbackStore:
    """``FeedbackStore`` over ``aiFeedbackEntries``."""

    def saveEntry(self, entry: AIFeedbackEntry) -> AIFeedbackEntry:
        row = AIFeedbackEntryModel.objects.create(
            id=entry.id,
            tenantId=entry.tenantId,
            requestId=entry.requestId,
            responseId=entry.responseId,
            userId=entry.userId,
            kind=entry.kind,
            rating=entry.rating,
            sentiment=entry.sentiment,
            reason=entry.reason,
            comment=entry.comment,
            correction=entry.correction,
            question=entry.question,
            modelCode=entry.modelCode,
            promptVersion=entry.promptVersion,
            capabilityCode=entry.capabilityCode,
            suiteCode=entry.suiteCode,
            status=entry.status,
            promotedCaseCode=entry.promotedCaseCode,
            rejectionReason=entry.rejectionReason,
            triagedBy=entry.triagedBy,
            triagedAt=entry.triagedAt,
            fingerprint=entry.fingerprint,
            metadata=dict(entry.metadata),
        )
        # ``createdAt``/``updatedAt`` are auto_now_add/auto_now columns, so
        # Django ignores the values the domain computed. Trend windows are
        # built on those timestamps, so the domain clock has to win: the
        # values are written back explicitly right after the insert.
        AIFeedbackEntryModel.objects.filter(id=row.id).update(
            createdAt=entry.createdAt, updatedAt=entry.updatedAt
        )
        return feedbackToEntity(AIFeedbackEntryModel.objects.get(id=row.id))

    def updateEntry(self, entry: AIFeedbackEntry) -> AIFeedbackEntry:
        updated = AIFeedbackEntryModel.objects.filter(tenantId=entry.tenantId, id=entry.id).update(
            rating=entry.rating,
            sentiment=entry.sentiment,
            reason=entry.reason,
            comment=entry.comment,
            correction=entry.correction,
            status=entry.status,
            promotedCaseCode=entry.promotedCaseCode,
            rejectionReason=entry.rejectionReason,
            suiteCode=entry.suiteCode,
            triagedBy=entry.triagedBy,
            triagedAt=entry.triagedAt,
            updatedAt=entry.updatedAt,
            metadata=dict(entry.metadata),
        )
        if not updated:
            raise AIFeedbackInvalid("Feedback row was not found for update.")
        return feedbackToEntity(
            AIFeedbackEntryModel.objects.get(tenantId=entry.tenantId, id=entry.id)
        )

    def getEntry(self, tenantId: uuid.UUID, feedbackId: uuid.UUID) -> AIFeedbackEntry | None:
        row = AIFeedbackEntryModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            id=requireUuid(feedbackId, "feedbackId"),
        ).first()
        return None if row is None else feedbackToEntity(row)

    def findByFingerprint(self, tenantId: uuid.UUID, fingerprint: str) -> AIFeedbackEntry | None:
        row = AIFeedbackEntryModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            fingerprint=str(fingerprint or "").strip().lower(),
        ).first()
        return None if row is None else feedbackToEntity(row)

    def listEntries(
        self,
        tenantId: uuid.UUID,
        *,
        statuses: tuple[str, ...] = (),
        sentiments: tuple[str, ...] = (),
        requestId: uuid.UUID | None = None,
        modelCode: str = "",
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 500,
    ) -> tuple[AIFeedbackEntry, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if statuses:
            query &= Q(status__in=[str(value).strip().upper() for value in statuses])
        if sentiments:
            query &= Q(sentiment__in=[str(value).strip().upper() for value in sentiments])
        if requestId is not None:
            query &= Q(requestId=requireUuid(requestId, "requestId"))
        if modelCode:
            query &= Q(modelCode=str(modelCode).strip().upper())
        if since is not None:
            query &= Q(createdAt__gte=since)
        if until is not None:
            query &= Q(createdAt__lt=until)
        rows = AIFeedbackEntryModel.objects.filter(query).order_by("createdAt", "id")[
            : max(1, int(limit))
        ]
        return tuple(feedbackToEntity(row) for row in rows)

    def countByStatus(self, tenantId: uuid.UUID) -> dict[str, int]:
        rows = AIFeedbackEntryModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId")
        ).values_list("status", flat=True)
        counts: dict[str, int] = {}
        for status in rows:
            counts[status] = counts.get(status, 0) + 1
        return dict(sorted(counts.items()))

    def deleteEntriesBefore(self, tenantId: uuid.UUID | None, cutoff: datetime) -> int:
        query = AIFeedbackEntryModel.objects.filter(
            createdAt__lt=cutoff, status__in=list(TERMINAL_FEEDBACK_STATUSES)
        )
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        removed, _ = query.delete()
        return int(removed)


__all__ = [
    "DjangoFeedbackStore",
    "feedbackToEntity",
]
