"""Phase 12 notification aggregates — the canonical multi-recipient model.

Framework-free (no Django/ORM). The Phase 09 single-recipient notification row
stays untouched; these records implement §12.3/§12.7/§12.8 correctly:

* ``BroadcastNotification`` — ONE notification, MANY recipients. Read state
  lives on each recipient (``NotificationRecipient``), never on the
  notification itself (§12.8 forbids ``Notification.isRead``).
* ``RecipientDelivery`` — one channel delivery for one recipient (§12.14),
  with a state machine (§12.15) and per-attempt records (§12.16).
* ``DeliveryAttempt`` — an audited send attempt (§12.16).
* ``NotificationRule`` — a WHEN/IF/THEN routing rule (§12.24).
* ``InboundNotificationEvent`` — the idempotent event-bus envelope (§12.38).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.notifications.domain.valueObjects import phase12Types as t
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import (
    ConflictError,
    ValidationFailedError,
)

# ---------------------------------------------------------------------------
# §12.16 DeliveryAttempt
# ---------------------------------------------------------------------------


class DeliveryAttempt(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        deliveryId: uuid.UUID,
        attemptNumber: int,
        *,
        status: str = t.ATTEMPT_FAILED,
        provider: str = "",
        providerMessageId: str = "",
        errorCode: str = "",
        errorMessage: str = "",
        responseMetadata: dict[str, Any] | None = None,
        startedAt: datetime | None = None,
        completedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        t.validateOneOf(status, t.ATTEMPT_OUTCOMES, field="attemptStatus")
        self.tenantId = tenantId
        self.deliveryId = deliveryId
        self.attemptNumber = attemptNumber
        self.status = status
        self.provider = provider
        self.providerMessageId = providerMessageId
        self.errorCode = errorCode
        self.errorMessage = errorMessage
        self.responseMetadata = responseMetadata or {}
        self.startedAt = startedAt
        self.completedAt = completedAt

    @staticmethod
    def record(
        tenantId: uuid.UUID,
        deliveryId: uuid.UUID,
        attemptNumber: int,
        startedAt: datetime,
        *,
        succeeded: bool,
        delivered: bool = False,
        provider: str = "",
        providerMessageId: str = "",
        errorCode: str = "",
        errorMessage: str = "",
        responseMetadata: dict[str, Any] | None = None,
    ) -> DeliveryAttempt:
        status = t.ATTEMPT_DELIVERED if delivered else (
            t.ATTEMPT_SENT if succeeded else t.ATTEMPT_FAILED
        )
        return DeliveryAttempt(
            id=newId(),
            tenantId=tenantId,
            deliveryId=deliveryId,
            attemptNumber=attemptNumber,
            status=status,
            provider=provider,
            providerMessageId=providerMessageId,
            errorCode=errorCode,
            errorMessage=errorMessage,
            responseMetadata=responseMetadata,
            startedAt=startedAt,
            completedAt=startedAt,
        )


# ---------------------------------------------------------------------------
# §12.14/§12.15 RecipientDelivery — channel delivery for one recipient
# ---------------------------------------------------------------------------


class RecipientDelivery(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        notificationId: uuid.UUID,
        recipientId: uuid.UUID,
        channel: str,
        *,
        provider: str = "",
        status: str = t.DLV_PENDING,
        attemptCount: int = 0,
        maxAttempts: int = t.DEFAULT_MAX_ATTEMPTS,
        errorCode: str = "",
        errorMessage: str = "",
        lastAttemptAt: datetime | None = None,
        nextAttemptAt: datetime | None = None,
        deliveredAt: datetime | None = None,
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        t.validateOneOf(status, t.DELIVERY_LIFECYCLE, field="deliveryStatus")
        self.tenantId = tenantId
        self.notificationId = notificationId
        self.recipientId = recipientId
        self.channel = channel
        self.provider = provider
        self.status = status
        self.attemptCount = attemptCount
        self.maxAttempts = maxAttempts
        self.errorCode = errorCode
        self.errorMessage = errorMessage
        self.lastAttemptAt = lastAttemptAt
        self.nextAttemptAt = nextAttemptAt
        self.deliveredAt = deliveredAt
        self.createdAt = createdAt

    @staticmethod
    def queue(
        tenantId: uuid.UUID,
        notificationId: uuid.UUID,
        recipientId: uuid.UUID,
        channel: str,
        now: datetime,
    ) -> RecipientDelivery:
        d = RecipientDelivery(
            id=newId(),
            tenantId=tenantId,
            notificationId=notificationId,
            recipientId=recipientId,
            channel=channel,
            status=t.DLV_QUEUED,
            nextAttemptAt=now,  # due immediately; retry delays set later (§12.17)
            createdAt=now,
        )
        d.recordEvent(
            DomainEvent(
                name="notificationDeliveryQueued",
                occurredAt=now,
                tenantId=tenantId,
                payload={"notificationId": str(notificationId), "channel": channel},
            )
        )
        return d

    def _transition(self, target: str, now: datetime) -> None:
        if target not in t.DELIVERY_TRANSITIONS.get(self.status, ()):
            raise ConflictError(
                f"Cannot move delivery {self.status} -> {target}."
            )
        self.status = target

    def markProcessing(self, now: datetime) -> None:
        self._transition(t.DLV_PROCESSING, now)

    def recordAttempt(
        self,
        now: datetime,
        *,
        succeeded: bool,
        delivered: bool,
        retryPolicy: t.RetryPolicy,
        provider: str = "",
        providerMessageId: str = "",
        errorCode: str = "",
        errorMessage: str = "",
    ) -> DeliveryAttempt:
        """Record an attempt and advance SENT/DELIVERED or schedule a retry /
        dead-letter (§12.16/§12.17/§12.18)."""
        self.attemptCount += 1
        self.lastAttemptAt = now
        attempt = DeliveryAttempt.record(
            self.tenantId,
            self.id,
            self.attemptCount,
            now,
            succeeded=succeeded,
            delivered=delivered,
            provider=provider,
            providerMessageId=providerMessageId,
            errorCode=errorCode,
            errorMessage=errorMessage,
        )
        if delivered:
            self._transition(t.DLV_DELIVERED, now)
            self.deliveredAt = now
            self.nextAttemptAt = None
            self.errorCode = ""
            self.errorMessage = ""
        elif succeeded:
            self._transition(t.DLV_SENT, now)
            self.nextAttemptAt = None
        else:
            self.errorCode = errorCode
            self.errorMessage = errorMessage
            if retryPolicy.isExhausted(self.attemptCount):
                # all retries spent -> dead letter (§12.18)
                self.status = t.DLV_FAILED
                self._transition(t.DLV_DEAD_LETTER, now)
                self.nextAttemptAt = None
                self.recordEvent(
                    DomainEvent(
                        name="notificationDeliveryDeadLettered",
                        occurredAt=now,
                        tenantId=self.tenantId,
                        payload={
                            "deliveryId": str(self.id),
                            "attemptCount": self.attemptCount,
                        },
                    )
                )
            else:
                self.status = t.DLV_FAILED
                self._transition(t.DLV_QUEUED, now)
                delay = retryPolicy.delayForAttempt(self.attemptCount + 1)
                from datetime import timedelta

                self.nextAttemptAt = now + timedelta(seconds=delay)
                self.recordEvent(
                    DomainEvent(
                        name="notificationRetryScheduled",
                        occurredAt=now,
                        tenantId=self.tenantId,
                        payload={
                            "deliveryId": str(self.id),
                            "nextAttemptAt": self.nextAttemptAt.isoformat(),
                            "attemptNumber": self.attemptCount + 1,
                        },
                    )
                )
        return attempt

    def cancel(self, now: datetime) -> None:
        self._transition(t.DLV_CANCELLED, now)

    def expire(self, now: datetime) -> None:
        self._transition(t.DLV_EXPIRED, now)


# ---------------------------------------------------------------------------
# §12.7 NotificationRecipient — owns read/archive state
# ---------------------------------------------------------------------------


class NotificationRecipient(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        notificationId: uuid.UUID,
        userId: uuid.UUID,
        *,
        state: str = t.RECIPIENT_UNREAD,
        readAt: datetime | None = None,
        archivedAt: datetime | None = None,
        dismissedAt: datetime | None = None,
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        t.validateOneOf(state, t.RECIPIENT_STATES, field="recipientState")
        self.tenantId = tenantId
        self.notificationId = notificationId
        self.userId = userId
        self.state = state
        self.readAt = readAt
        self.archivedAt = archivedAt
        self.dismissedAt = dismissedAt
        self.createdAt = createdAt

    @staticmethod
    def attach(
        tenantId: uuid.UUID, notificationId: uuid.UUID, userId: uuid.UUID, now: datetime
    ) -> NotificationRecipient:
        return NotificationRecipient(
            id=newId(),
            tenantId=tenantId,
            notificationId=notificationId,
            userId=userId,
            createdAt=now,
        )

    def _move(self, target: str, now: datetime) -> None:
        if target not in t.RECIPIENT_TRANSITIONS.get(self.state, ()):
            raise ConflictError(
                f"Cannot move recipient {self.state} -> {target}."
            )
        self.state = target

    def markRead(self, now: datetime) -> None:
        if self.state == t.RECIPIENT_UNREAD:
            self._move(t.RECIPIENT_READ, now)
            self.readAt = now
        elif self.state in (t.RECIPIENT_ARCHIVED, t.RECIPIENT_DISMISSED):
            # re-reading an archived/dismissed item restores READ
            self.state = t.RECIPIENT_READ
            self.readAt = now

    def markUnread(self, now: datetime) -> None:
        if self.state != t.RECIPIENT_UNREAD:
            self.state = t.RECIPIENT_UNREAD
            self.readAt = None

    def archive(self, now: datetime) -> None:
        self._move(t.RECIPIENT_ARCHIVED, now)
        self.archivedAt = now

    def dismiss(self, now: datetime) -> None:
        self._move(t.RECIPIENT_DISMISSED, now)
        self.dismissedAt = now


# ---------------------------------------------------------------------------
# §12.3 BroadcastNotification — one notification, many recipients
# ---------------------------------------------------------------------------


class BroadcastNotification(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        notificationType: str,
        title: str,
        body: str,
        *,
        priority: str = "NORMAL",
        severity: str = t.SEVERITY_INFO,
        sourceType: str = "",
        sourceId: str = "",
        deepLink: str = "",
        metadata: dict[str, Any] | None = None,
        language: str = "",
        idempotencyKey: str = "",
        correlationId: str = "",
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if not title.strip():
            raise ValidationFailedError("title is required.", fieldErrors={"title": "empty"})
        t.validateOneOf(severity, t.SEVERITIES, field="severity")
        self.tenantId = tenantId
        self.notificationType = notificationType
        self.title = title.strip()
        self.body = body
        self.priority = priority
        self.severity = severity
        self.sourceType = sourceType
        self.sourceId = sourceId
        self.deepLink = deepLink
        self.metadata = metadata or {}
        self.language = language
        self.idempotencyKey = idempotencyKey
        self.correlationId = correlationId
        self.createdAt = createdAt
        self.recipients: list[NotificationRecipient] = []

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        notificationType: str,
        title: str,
        body: str,
        recipientIds: list[uuid.UUID],
        now: datetime,
        *,
        priority: str = "NORMAL",
        severity: str = t.SEVERITY_INFO,
        sourceType: str = "",
        sourceId: str = "",
        deepLink: str = "",
        metadata: dict[str, Any] | None = None,
        language: str = "",
        idempotencyKey: str = "",
        correlationId: str = "",
    ) -> BroadcastNotification:
        if not recipientIds:
            raise ValidationFailedError(
                "at least one recipient required.",
                fieldErrors={"recipientIds": "empty"},
            )
        notification = BroadcastNotification(
            id=newId(),
            tenantId=tenantId,
            notificationType=notificationType,
            title=title,
            body=body,
            priority=priority,
            severity=severity,
            sourceType=sourceType,
            sourceId=sourceId,
            deepLink=deepLink,
            metadata=metadata,
            language=language,
            idempotencyKey=idempotencyKey,
            correlationId=correlationId,
            createdAt=now,
        )
        seen: set[uuid.UUID] = set()
        for userId in recipientIds:
            if userId in seen:
                continue
            seen.add(userId)
            notification.recipients.append(
                NotificationRecipient.attach(tenantId, notification.id, userId, now)
            )
        notification.recordEvent(
            DomainEvent(
                name="notificationCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={
                    "notificationId": str(notification.id),
                    "recipientCount": len(notification.recipients),
                    "type": notificationType,
                },
            )
        )
        return notification

    def recipientFor(self, userId: uuid.UUID) -> NotificationRecipient | None:
        for recipient in self.recipients:
            if recipient.userId == userId:
                return recipient
        return None

    def isUnreadFor(self, userId: uuid.UUID) -> bool:
        recipient = self.recipientFor(userId)
        return recipient is not None and recipient.state == t.RECIPIENT_UNREAD


# ---------------------------------------------------------------------------
# §12.24 NotificationRule — WHEN event / IF condition / THEN notify
# ---------------------------------------------------------------------------


class NotificationRule(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        name: str,
        eventType: str,
        *,
        condition: dict[str, Any] | None = None,
        recipientStrategy: str = "TARGET",  # TARGET | MANAGER | ASSIGNEE | ROLE
        channels: tuple[str, ...] = (),
        priority: str = "NORMAL",
        templateKey: str = "",
        isActive: bool = True,
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if not name.strip():
            raise ValidationFailedError("rule name required.", fieldErrors={"name": "empty"})
        if not eventType.strip():
            raise ValidationFailedError("eventType required.", fieldErrors={"eventType": "empty"})
        self.tenantId = tenantId
        self.name = name.strip()
        self.eventType = eventType
        self.condition = condition or {}
        self.recipientStrategy = recipientStrategy
        self.channels = tuple(channels)
        self.priority = priority
        self.templateKey = templateKey or eventType
        self.isActive = isActive
        self.createdAt = createdAt

    @staticmethod
    def define(
        tenantId: uuid.UUID,
        name: str,
        eventType: str,
        now: datetime,
        *,
        condition: dict[str, Any] | None = None,
        recipientStrategy: str = "TARGET",
        channels: tuple[str, ...] = (),
        priority: str = "NORMAL",
        templateKey: str = "",
    ) -> NotificationRule:
        return NotificationRule(
            id=newId(),
            tenantId=tenantId,
            name=name,
            eventType=eventType,
            condition=condition,
            recipientStrategy=recipientStrategy,
            channels=channels,
            priority=priority,
            templateKey=templateKey,
            createdAt=now,
        )

    def matches(self, eventType: str, payload: dict[str, Any]) -> bool:
        """Evaluate the IF clause against the event payload (§12.24).

        Conditions are simple ``{field: expectedValue}`` equality checks on
        top-level payload keys; an empty condition matches the event type only.
        """
        if not self.isActive or self.eventType != eventType:
            return False
        for key, expected in self.condition.items():
            if payload.get(key) != expected:
                return False
        return True


# ---------------------------------------------------------------------------
# §12.38 InboundNotificationEvent — idempotent event-bus envelope
# ---------------------------------------------------------------------------


class InboundNotificationEvent(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        eventId: str,
        eventType: str,
        *,
        payload: dict[str, Any] | None = None,
        processed: bool = False,
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if not eventId.strip():
            raise ValidationFailedError("eventId required.", fieldErrors={"eventId": "empty"})
        self.tenantId = tenantId
        self.eventId = eventId
        self.eventType = eventType
        self.payload = payload or {}
        self.processed = processed
        self.createdAt = createdAt

    @staticmethod
    def ingest(
        tenantId: uuid.UUID, eventId: str, eventType: str, now: datetime,
        payload: dict[str, Any] | None = None,
    ) -> InboundNotificationEvent:
        return InboundNotificationEvent(
            id=newId(),
            tenantId=tenantId,
            eventId=eventId,
            eventType=eventType,
            payload=payload,
            createdAt=now,
        )

    def markProcessed(self) -> None:
        self.processed = True
