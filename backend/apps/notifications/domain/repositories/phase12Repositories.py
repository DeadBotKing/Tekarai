"""Phase 12 repository ports for the multi-recipient notification model.

Protocols only; Django implementations live in infrastructure. Every query is
explicitly tenant-scoped (§12.25).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from apps.notifications.domain.entities.phase12Records import (
    BroadcastNotification,
    DeliveryAttempt,
    InboundNotificationEvent,
    NotificationRecipient,
    NotificationRule,
    RecipientDelivery,
)


@runtime_checkable
class BroadcastNotificationRepository(Protocol):
    def save(self, notification: BroadcastNotification) -> None:
        """Persist the notification AND its recipients in one transaction."""

    def getById(
        self, tenantId: uuid.UUID, notificationId: uuid.UUID
    ) -> BroadcastNotification | None: ...

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, idempotencyKey: str
    ) -> BroadcastNotification | None: ...

    def listForRecipient(
        self,
        tenantId: uuid.UUID,
        recipientId: uuid.UUID,
        *,
        unreadOnly: bool = False,
        limit: int = 50,
    ) -> list[BroadcastNotification]: ...

    def unreadCount(self, tenantId: uuid.UUID, recipientId: uuid.UUID) -> int: ...

    def getRecipient(
        self,
        tenantId: uuid.UUID,
        notificationId: uuid.UUID,
        userId: uuid.UUID,
    ) -> NotificationRecipient | None: ...

    def saveRecipient(self, recipient: NotificationRecipient) -> None: ...


@runtime_checkable
class RecipientDeliveryRepository(Protocol):
    def save(self, delivery: RecipientDelivery) -> None: ...

    def saveAttempt(self, attempt: DeliveryAttempt) -> None: ...

    def getById(
        self, tenantId: uuid.UUID, deliveryId: uuid.UUID
    ) -> RecipientDelivery | None: ...

    def listForNotification(
        self, tenantId: uuid.UUID, notificationId: uuid.UUID
    ) -> list[RecipientDelivery]: ...

    def listRetryDue(
        self, now: datetime, *, limit: int = 100
    ) -> list[RecipientDelivery]: ...

    def listDeadLetter(
        self, tenantId: uuid.UUID, *, limit: int = 100
    ) -> list[RecipientDelivery]: ...

    def listAttempts(
        self, tenantId: uuid.UUID, deliveryId: uuid.UUID
    ) -> list[DeliveryAttempt]: ...


@runtime_checkable
class NotificationRuleRepository(Protocol):
    def save(self, rule: NotificationRule) -> None: ...

    def getById(
        self, tenantId: uuid.UUID, ruleId: uuid.UUID
    ) -> NotificationRule | None: ...

    def listForEvent(
        self, tenantId: uuid.UUID, eventType: str
    ) -> list[NotificationRule]: ...

    def listActive(self, tenantId: uuid.UUID) -> list[NotificationRule]: ...


@runtime_checkable
class InboundEventRepository(Protocol):
    def save(self, event: InboundNotificationEvent) -> None: ...

    def findProcessed(
        self, tenantId: uuid.UUID, eventId: str
    ) -> InboundNotificationEvent | None: ...

    def markProcessed(self, event: InboundNotificationEvent) -> None: ...
