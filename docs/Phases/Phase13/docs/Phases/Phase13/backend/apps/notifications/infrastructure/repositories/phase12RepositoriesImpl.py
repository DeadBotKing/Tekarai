"""Phase 12 Django repository implementations — multi-recipient model.

Thin ORM <-> domain mappers. Every read/write is tenant-scoped (§12.25). No
business logic lives here (§12.43 query logic belongs to selectors; these are
persistence adapters only).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from apps.notifications.domain.entities import phase12Records as d
from apps.notifications.infrastructure.models import (
    NotificationAttemptModel,
    NotificationEventModel,
    NotificationModel,
    NotificationRecipientDeliveryModel,
    NotificationRecipientModel,
    NotificationRuleModel,
)


def _now() -> datetime:
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Broadcast notification + recipients
# ---------------------------------------------------------------------------


class BroadcastNotificationRepositoryDjango:
    def save(self, notification: d.BroadcastNotification) -> None:
        NotificationModel.objects.update_or_create(
            id=notification.id,
            defaults={
                "tenantId": notification.tenantId,
                "notificationType": notification.notificationType,
                "severity": notification.severity,
                "priority": notification.priority,
                "title": notification.title,
                "body": notification.body,
                "sourceType": notification.sourceType,
                "sourceId": notification.sourceId,
                "deepLink": notification.deepLink,
                "language": notification.language,
                "metadata": notification.metadata,
                "idempotencyKey": notification.idempotencyKey,
                "correlationId": notification.correlationId,
                "createdAt": notification.createdAt or _now(),
            },
        )
        for recipient in notification.recipients:
            NotificationRecipientModel.objects.get_or_create(
                id=recipient.id,
                defaults={
                    "tenantId": recipient.tenantId,
                    "notificationId": recipient.notificationId,
                    "userId": recipient.userId,
                    "recipientState": recipient.state,
                    "readAt": recipient.readAt,
                    "archivedAt": recipient.archivedAt,
                    "dismissedAt": recipient.dismissedAt,
                    "createdAt": recipient.createdAt or _now(),
                },
            )

    def getById(
        self, tenantId: uuid.UUID, notificationId: uuid.UUID
    ) -> d.BroadcastNotification | None:
        model = NotificationModel.objects.filter(
            tenantId=tenantId, id=notificationId
        ).first()
        if model is None:
            return None
        return self._toDomain(model)

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, idempotencyKey: str
    ) -> d.BroadcastNotification | None:
        if not idempotencyKey:
            return None
        model = NotificationModel.objects.filter(
            tenantId=tenantId, idempotencyKey=idempotencyKey
        ).first()
        return self._toDomain(model) if model else None

    def listForRecipient(
        self,
        tenantId: uuid.UUID,
        recipientId: uuid.UUID,
        *,
        unreadOnly: bool = False,
        limit: int = 50,
    ) -> list[d.BroadcastNotification]:
        rows = NotificationRecipientModel.objects.filter(
            tenantId=tenantId, userId=recipientId
        )
        if unreadOnly:
            rows = rows.filter(recipientState="UNREAD")
        ids = list(rows.values_list("notificationId", flat=True))[: limit * 2]
        notifications = list(
            NotificationModel.objects.filter(
                tenantId=tenantId, id__in=ids
            ).order_by("-createdAt")[:limit]
        )
        return [self._toDomain(n) for n in notifications]

    def unreadCount(self, tenantId: uuid.UUID, recipientId: uuid.UUID) -> int:
        return NotificationRecipientModel.objects.filter(
            tenantId=tenantId, userId=recipientId, recipientState="UNREAD"
        ).count()

    def getRecipient(
        self, tenantId: uuid.UUID, notificationId: uuid.UUID, userId: uuid.UUID
    ) -> d.NotificationRecipient | None:
        model = NotificationRecipientModel.objects.filter(
            tenantId=tenantId, notificationId=notificationId, userId=userId
        ).first()
        return self._recipientToDomain(model) if model else None

    def saveRecipient(self, recipient: d.NotificationRecipient) -> None:
        NotificationRecipientModel.objects.update_or_create(
            id=recipient.id,
            defaults={
                "tenantId": recipient.tenantId,
                "notificationId": recipient.notificationId,
                "userId": recipient.userId,
                "recipientState": recipient.state,
                "readAt": recipient.readAt,
                "archivedAt": recipient.archivedAt,
                "dismissedAt": recipient.dismissedAt,
            },
        )

    # -- mappers -------------------------------------------------------------

    @staticmethod
    def _recipientToDomain(model: NotificationRecipientModel) -> d.NotificationRecipient:
        return d.NotificationRecipient(
            id=model.id,
            tenantId=model.tenantId,
            notificationId=model.notificationId,
            userId=model.userId,
            state=model.recipientState,
            readAt=model.readAt,
            archivedAt=model.archivedAt,
            dismissedAt=model.dismissedAt,
            createdAt=model.createdAt,
        )

    def _toDomain(self, model: NotificationModel) -> d.BroadcastNotification:
        notification = d.BroadcastNotification(
            id=model.id,
            tenantId=model.tenantId,
            notificationType=model.notificationType,
            title=model.title,
            body=model.body,
            priority=model.priority,
            severity=model.severity,
            sourceType=model.sourceType,
            sourceId=model.sourceId,
            deepLink=model.deepLink,
            metadata=model.metadata or {},
            language=model.language,
            idempotencyKey=model.idempotencyKey,
            correlationId=model.correlationId,
            createdAt=model.createdAt,
        )
        notification.recipients = [
            self._recipientToDomain(r)
            for r in NotificationRecipientModel.objects.filter(
                tenantId=model.tenantId, notificationId=model.id
            )
        ]
        return notification


# ---------------------------------------------------------------------------
# Recipient deliveries + attempts
# ---------------------------------------------------------------------------


class RecipientDeliveryRepositoryDjango:
    def save(self, delivery: d.RecipientDelivery) -> None:
        NotificationRecipientDeliveryModel.objects.update_or_create(
            id=delivery.id,
            defaults={
                "tenantId": delivery.tenantId,
                "notificationId": delivery.notificationId,
                "recipientId": delivery.recipientId,
                "channel": delivery.channel,
                "provider": delivery.provider,
                "deliveryStatus": delivery.status,
                "attemptCount": delivery.attemptCount,
                "maxAttempts": delivery.maxAttempts,
                "errorCode": delivery.errorCode,
                "errorMessage": delivery.errorMessage,
                "lastAttemptAt": delivery.lastAttemptAt,
                "nextAttemptAt": delivery.nextAttemptAt,
                "deliveredAt": delivery.deliveredAt,
            },
        )

    def saveAttempt(self, attempt: d.DeliveryAttempt) -> None:
        NotificationAttemptModel.objects.get_or_create(
            id=attempt.id,
            defaults={
                "tenantId": attempt.tenantId,
                "deliveryId": attempt.deliveryId,
                "attemptNumber": attempt.attemptNumber,
                "outcome": attempt.status,
                "provider": attempt.provider,
                "providerMessageId": attempt.providerMessageId,
                "errorCode": attempt.errorCode,
                "errorMessage": attempt.errorMessage,
                "responseMetadata": attempt.responseMetadata,
                "startedAt": attempt.startedAt,
                "completedAt": attempt.completedAt,
            },
        )

    def getById(
        self, tenantId: uuid.UUID, deliveryId: uuid.UUID
    ) -> d.RecipientDelivery | None:
        model = NotificationRecipientDeliveryModel.objects.filter(
            tenantId=tenantId, id=deliveryId
        ).first()
        return self._toDomain(model) if model else None

    def listForNotification(
        self, tenantId: uuid.UUID, notificationId: uuid.UUID
    ) -> list[d.RecipientDelivery]:
        return [
            self._toDomain(m)
            for m in NotificationRecipientDeliveryModel.objects.filter(
                tenantId=tenantId, notificationId=notificationId
            )
        ]

    def listRetryDue(self, now: datetime, *, limit: int = 100) -> list[d.RecipientDelivery]:
        return [
            self._toDomain(m)
            for m in NotificationRecipientDeliveryModel.objects.filter(
                deliveryStatus="QUEUED",
                nextAttemptAt__lte=now,
            ).order_by("nextAttemptAt")[:limit]
        ]

    def listDeadLetter(
        self, tenantId: uuid.UUID, *, limit: int = 100
    ) -> list[d.RecipientDelivery]:
        return [
            self._toDomain(m)
            for m in NotificationRecipientDeliveryModel.objects.filter(
                tenantId=tenantId, deliveryStatus="DEAD_LETTER"
            ).order_by("-lastAttemptAt")[:limit]
        ]

    def listAttempts(
        self, tenantId: uuid.UUID, deliveryId: uuid.UUID
    ) -> list[d.DeliveryAttempt]:
        return [
            d.DeliveryAttempt(
                id=m.id,
                tenantId=m.tenantId,
                deliveryId=m.deliveryId,
                attemptNumber=m.attemptNumber,
                status=m.outcome,
                provider=m.provider,
                providerMessageId=m.providerMessageId,
                errorCode=m.errorCode,
                errorMessage=m.errorMessage,
                responseMetadata=m.responseMetadata or {},
                startedAt=m.startedAt,
                completedAt=m.completedAt,
            )
            for m in NotificationAttemptModel.objects.filter(
                tenantId=tenantId, deliveryId=deliveryId
            ).order_by("attemptNumber")
        ]

    @staticmethod
    def _toDomain(model: NotificationRecipientDeliveryModel) -> d.RecipientDelivery:
        return d.RecipientDelivery(
            id=model.id,
            tenantId=model.tenantId,
            notificationId=model.notificationId,
            recipientId=model.recipientId,
            channel=model.channel,
            provider=model.provider,
            status=model.deliveryStatus,
            attemptCount=model.attemptCount,
            maxAttempts=model.maxAttempts,
            errorCode=model.errorCode,
            errorMessage=model.errorMessage,
            lastAttemptAt=model.lastAttemptAt,
            nextAttemptAt=model.nextAttemptAt,
            deliveredAt=model.deliveredAt,
            createdAt=model.createdAt,
        )


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class NotificationRuleRepositoryDjango:
    def save(self, rule: d.NotificationRule) -> None:
        NotificationRuleModel.objects.update_or_create(
            id=rule.id,
            defaults={
                "tenantId": rule.tenantId,
                "name": rule.name,
                "eventType": rule.eventType,
                "condition": rule.condition,
                "recipientStrategy": rule.recipientStrategy,
                "channels": list(rule.channels),
                "priority": rule.priority,
                "templateKey": rule.templateKey,
                "isActive": rule.isActive,
                "createdAt": rule.createdAt or _now(),
            },
        )

    def getById(self, tenantId: uuid.UUID, ruleId: uuid.UUID) -> d.NotificationRule | None:
        model = NotificationRuleModel.objects.filter(tenantId=tenantId, id=ruleId).first()
        return self._toDomain(model) if model else None

    def listForEvent(self, tenantId: uuid.UUID, eventType: str) -> list[d.NotificationRule]:
        return [
            self._toDomain(m)
            for m in NotificationRuleModel.objects.filter(
                tenantId=tenantId, eventType=eventType, isActive=True
            )
        ]

    def listActive(self, tenantId: uuid.UUID) -> list[d.NotificationRule]:
        return [
            self._toDomain(m)
            for m in NotificationRuleModel.objects.filter(
                tenantId=tenantId, isActive=True
            )
        ]

    @staticmethod
    def _toDomain(model: NotificationRuleModel) -> d.NotificationRule:
        return d.NotificationRule(
            id=model.id,
            tenantId=model.tenantId,
            name=model.name,
            eventType=model.eventType,
            condition=model.condition or {},
            recipientStrategy=model.recipientStrategy,
            channels=tuple(model.channels or ()),
            priority=model.priority,
            templateKey=model.templateKey,
            isActive=model.isActive,
            createdAt=model.createdAt,
        )


# ---------------------------------------------------------------------------
# Inbound events (idempotency)
# ---------------------------------------------------------------------------


class InboundEventRepositoryDjango:
    def save(self, event: d.InboundNotificationEvent) -> None:
        NotificationEventModel.objects.get_or_create(
            eventId=event.eventId,
            tenantId=event.tenantId,
            defaults={
                "id": event.id,
                "eventType": event.eventType,
                "payload": event.payload,
                "processed": event.processed,
                "createdAt": event.createdAt or _now(),
            },
        )

    def findProcessed(
        self, tenantId: uuid.UUID, eventId: str
    ) -> d.InboundNotificationEvent | None:
        model = NotificationEventModel.objects.filter(
            tenantId=tenantId, eventId=eventId, processed=True
        ).first()
        if model is None:
            return None
        return d.InboundNotificationEvent(
            id=model.id,
            tenantId=model.tenantId,
            eventId=model.eventId,
            eventType=model.eventType,
            payload=model.payload or {},
            processed=model.processed,
            createdAt=model.createdAt,
        )

    def markProcessed(self, event: d.InboundNotificationEvent) -> None:
        NotificationEventModel.objects.filter(
            tenantId=event.tenantId, eventId=event.eventId
        ).update(processed=True)
