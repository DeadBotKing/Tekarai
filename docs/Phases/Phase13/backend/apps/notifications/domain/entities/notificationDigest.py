"""Digest aggregates (Phase 09 §21) + schedules (§22)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.notifications.domain.valueObjects.notificationTypes import (
    DIGEST_KINDS,
    DIGEST_STATUSES,
    DIGEST_STATUS_OPEN,
    DIGEST_STATUS_SENT,
    SCHEDULE_KINDS,
    SCHEDULE_PENDING,
    SCHEDULE_STATUSES,
)
from apps.sharedKernel.domain.entities import AggregateRoot
from apps.sharedKernel.domain.errors import ValidationFailedError


class NotificationDigest(AggregateRoot):
    """§21 — grouped notifications ('You have 20 task updates.')."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        kind: str,
        periodStart: datetime,
        periodEnd: datetime,
        *,
        status: str = DIGEST_STATUS_OPEN,
        itemCount: int = 0,
        sentAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if kind not in DIGEST_KINDS:
            raise ValidationFailedError(
                "Unknown digest kind.", fieldErrors={"kind": kind}
            )
        if status not in DIGEST_STATUSES:
            raise ValidationFailedError(
                "Unknown digest status.", fieldErrors={"status": status}
            )
        if periodEnd <= periodStart:
            raise ValidationFailedError(
                "Digest period end must be after start.",
                fieldErrors={"periodEnd": "order"},
            )
        self.tenantId = tenantId
        self.userId = userId
        self.kind = kind
        self.periodStart = periodStart
        self.periodEnd = periodEnd
        self.status = status
        self.itemCount = itemCount
        self.sentAt = sentAt

    def addItem(self) -> None:
        if self.status != DIGEST_STATUS_OPEN:
            raise ValidationFailedError("Cannot add items to a sent digest.")
        self.itemCount += 1

    def markSent(self, now: datetime) -> None:
        self.status = DIGEST_STATUS_SENT
        self.sentAt = now


class NotificationSchedule(AggregateRoot):
    """§22 — Immediate / Scheduled / Recurring / Delayed / Digest.

    The scheduler never depends on the frontend; the worker polls due rows.
    """

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        kind: str,
        *,
        recipientSpec: dict[str, Any],
        notificationType: str,
        category: str,
        priority: str,
        title: str,
        body: str = "",
        sourceType: str = "",
        sourceId: str = "",
        scheduledAt: datetime | None = None,
        recurEverySeconds: int = 0,
        status: str = SCHEDULE_PENDING,
        lastRunAt: datetime | None = None,
        nextRunAt: datetime | None = None,
        expiresAt: datetime | None = None,
        payload: dict[str, Any] | None = None,
        correlationId: str = "",
    ) -> None:
        super().__init__(id)
        if kind not in SCHEDULE_KINDS:
            raise ValidationFailedError(
                "Unknown schedule kind.", fieldErrors={"kind": kind}
            )
        if status not in SCHEDULE_STATUSES:
            raise ValidationFailedError(
                "Unknown schedule status.", fieldErrors={"status": status}
            )
        if kind == "RECURRING" and recurEverySeconds <= 0:
            raise ValidationFailedError(
                "RECURRING schedule needs recurEverySeconds > 0.",
                fieldErrors={"recurEverySeconds": "required"},
            )
        self.tenantId = tenantId
        self.kind = kind
        self.recipientSpec = recipientSpec
        self.notificationType = notificationType
        self.category = category
        self.priority = priority
        self.title = title
        self.body = body
        self.sourceType = sourceType
        self.sourceId = sourceId
        self.scheduledAt = scheduledAt
        self.recurEverySeconds = recurEverySeconds
        self.status = status
        self.lastRunAt = lastRunAt
        self.nextRunAt = nextRunAt or scheduledAt
        self.expiresAt = expiresAt
        self.payload = payload or {}
        self.correlationId = correlationId

    def isDue(self, now: datetime) -> bool:
        if self.status != SCHEDULE_PENDING:
            return False
        target = self.nextRunAt or self.scheduledAt
        return target is not None and target <= now

    def recordRun(self, now: datetime) -> bool:
        """Returns True when the schedule stays alive (recurring)."""
        self.lastRunAt = now
        if self.kind == "RECURRING":
            from datetime import timedelta

            self.nextRunAt = now + timedelta(seconds=self.recurEverySeconds)
            return True
        from apps.notifications.domain.valueObjects.notificationTypes import (
            SCHEDULE_DONE,
        )

        self.status = SCHEDULE_DONE
        return False

    def cancel(self) -> None:
        from apps.notifications.domain.valueObjects.notificationTypes import (
            SCHEDULE_CANCELLED,
        )

        self.status = SCHEDULE_CANCELLED
