"""Notification aggregate (Phase 09 §3, §23, §26)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.notifications.domain.valueObjects.notificationTypes import (
    NOTIFICATION_CANCELLED,
    NOTIFICATION_DELIVERED,
    NOTIFICATION_DISPATCHABLE,
    NOTIFICATION_EXPIRED,
    NOTIFICATION_FAILED,
    NOTIFICATION_PARTIALLY_DELIVERED,
    NOTIFICATION_PENDING,
    NOTIFICATION_PROCESSING,
    NOTIFICATION_STATUSES,
    NOTIFICATION_TERMINAL,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import (
    ConflictError,
    InvalidStateTransitionError,
    ValidationFailedError,
)


class Notification(AggregateRoot):
    """One notification targeted at ONE recipient (§3).

    Group recipients are resolved to individual notifications by the
    application layer (§9) — the aggregate itself is always single-recipient
    so delivery state, read state and acknowledgement stay unambiguous.
    """

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        recipientId: uuid.UUID,
        notificationType: str,
        category: str,
        title: str,
        body: str,
        priority: str,
        *,
        sourceType: str = "",
        sourceId: str = "",
        createdAt: datetime | None = None,
        scheduledAt: datetime | None = None,
        expiresAt: datetime | None = None,
        readAt: datetime | None = None,
        acknowledgedAt: datetime | None = None,
        status: str = NOTIFICATION_PENDING,
        idempotencyKey: str = "",
        requiresAcknowledgement: bool = False,
        language: str = "",
        correlationId: str = "",
        causationId: str = "",
        payload: dict[str, Any] | None = None,
        deletedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if status not in NOTIFICATION_STATUSES:
            raise ValidationFailedError(
                "Unknown notification status.", fieldErrors={"status": status}
            )
        if not title.strip():
            raise ValidationFailedError(
                "Notification title is required.", fieldErrors={"title": "empty"}
            )
        self.tenantId = tenantId
        self.recipientId = recipientId
        self.notificationType = notificationType
        self.category = category
        self.title = title
        self.body = body
        self.priority = priority
        self.sourceType = sourceType
        self.sourceId = sourceId
        self.createdAt = createdAt or datetime.now()
        self.scheduledAt = scheduledAt
        self.expiresAt = expiresAt
        self.readAt = readAt
        self.acknowledgedAt = acknowledgedAt
        self.status = status
        self.idempotencyKey = idempotencyKey
        self.requiresAcknowledgement = requiresAcknowledgement
        self.language = language
        self.correlationId = correlationId  # §46 distributed tracing
        self.causationId = causationId
        self.payload = payload or {}
        self.deletedAt = deletedAt

    # -- lifecycle -----------------------------------------------------------

    def isTerminal(self) -> bool:
        return self.status in NOTIFICATION_TERMINAL

    def isDispatchable(self) -> bool:
        return self.status in NOTIFICATION_DISPATCHABLE

    def isUnread(self) -> bool:
        return self.readAt is None and self.deletedAt is None

    def startProcessing(self, now: datetime) -> None:
        if self.status != NOTIFICATION_PENDING:
            raise InvalidStateTransitionError(
                f"Notification cannot move {self.status} → PROCESSING."
            )
        self.status = NOTIFICATION_PROCESSING

    def applyDeliveryOutcome(
        self, *, deliveredChannels: int, failedChannels: int, now: datetime
    ) -> None:
        """§47 — partial delivery is its own state, never a silent failure."""
        if self.status not in (NOTIFICATION_PENDING, NOTIFICATION_PROCESSING):
            return  # already terminal (e.g. expired mid-flight)
        if deliveredChannels > 0 and failedChannels == 0:
            self.status = NOTIFICATION_DELIVERED
        elif deliveredChannels > 0 and failedChannels > 0:
            self.status = NOTIFICATION_PARTIALLY_DELIVERED
        else:
            self.status = NOTIFICATION_FAILED
        self.recordEvent(
            DomainEvent(
                name="notificationDeliveryCompleted"
                if self.status != NOTIFICATION_FAILED
                else "notificationFailed",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"notificationId": str(self.id), "status": self.status},
            )
        )

    def cancel(self, now: datetime, *, actorId: uuid.UUID | None = None) -> None:
        if self.status in (NOTIFICATION_DELIVERED, NOTIFICATION_EXPIRED):
            raise ConflictError("Delivered/expired notifications cannot be cancelled.")
        if self.status == NOTIFICATION_CANCELLED:
            return  # idempotent
        self.status = NOTIFICATION_CANCELLED
        self.recordEvent(
            DomainEvent(
                name="notificationCancelled",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=actorId,
                payload={"notificationId": str(self.id)},
            )
        )

    def expire(self, now: datetime) -> bool:
        """§23 — expired notifications must not be delivered. Idempotent."""
        if self.status == NOTIFICATION_EXPIRED:
            return False
        if self.expiresAt is None or self.expiresAt > now:
            return False
        if self.status == NOTIFICATION_DELIVERED:
            return False
        self.status = NOTIFICATION_EXPIRED
        self.recordEvent(
            DomainEvent(
                name="notificationExpired",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"notificationId": str(self.id)},
            )
        )
        return True

    # §26 — read ≠ acknowledged

    def markRead(self, now: datetime) -> None:
        if self.readAt is not None:
            return  # idempotent
        self.readAt = now
        self.recordEvent(
            DomainEvent(
                name="notificationRead",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=self.recipientId,
                payload={"notificationId": str(self.id)},
            )
        )

    def markUnread(self, now: datetime) -> None:
        if self.readAt is None:
            return
        if self.acknowledgedAt is not None:
            raise ConflictError(
                "Acknowledged notifications cannot return to unread."
            )
        self.readAt = None

    def acknowledge(self, now: datetime, actorId: uuid.UUID) -> None:
        if self.acknowledgedAt is not None:
            return  # idempotent
        self.acknowledgedAt = now
        if self.readAt is None:
            self.markRead(now)
        self.recordEvent(
            DomainEvent(
                name="notificationAcknowledged",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=actorId,
                payload={"notificationId": str(self.id)},
            )
        )

    def archive(self, now: datetime) -> None:
        """§40 'Delete/Archive where allowed' — soft delete."""
        if self.deletedAt is not None:
            return
        self.deletedAt = now
