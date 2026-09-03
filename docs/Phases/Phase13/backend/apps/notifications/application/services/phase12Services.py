"""Phase 12 application services — multi-recipient notification platform.

Orchestrates the canonical model (docs/Phases/Phase12.md):
* ``CreateBroadcastService``   — one notification → many recipients (§12.3/§12.7)
* ``RecipientStateService``    — read/unread/archive/dismiss on the recipient (§12.8)
* ``BroadcastQueryService``    — inbox list + unread count (§12.43 selectors)
* ``DeliveryDispatchService``  — fan out per (recipient, channel) deliveries (§12.14)
* ``DeliveryRetryService``     — exponential backoff, dead-letter (§12.17/§12.18)
* ``RuleDefinitionService``    — WHEN/IF/THEN rules (§12.24)
* ``EventIntakeService``       — idempotent event-bus entry (§12.23/§12.38)

Business rules live in the domain; these services validate → apply → persist →
emit events/audit. External sends NEVER block the API (§12.40): deliveries are
created QUEUED and a worker processes them.
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.notifications.application.commands.phase12Commands import (
    CreateBroadcastCommand,
    DefineRuleCommand,
    IngestEventCommand,
    ListBroadcastsQuery,
    ListDeliveriesQuery,
    RecipientStateCommand,
    RetryDeliveryCommand,
    UnreadCountQuery,
)
from apps.notifications.application.services.notificationSupport import (
    NotificationUseCase,
)
from apps.notifications.domain.entities import phase12Records as records
from apps.notifications.domain.repositories.phase12Repositories import (
    BroadcastNotificationRepository,
    InboundEventRepository,
    NotificationRuleRepository,
    RecipientDeliveryRepository,
)
from apps.notifications.domain.valueObjects import phase12Types as types
from apps.sharedKernel.domain.errors import EntityNotFoundError
from apps.sharedKernel.domain.valueObjects import asUuid


def _actor() -> tuple[uuid.UUID, uuid.UUID]:
    from apps.sharedKernel.application.requestContext import currentContext

    context = currentContext()
    return asUuid(context.actorId), asUuid(context.actorTenantId)


# ---------------------------------------------------------------------------
# Broadcast creation
# ---------------------------------------------------------------------------


class CreateBroadcastService(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        broadcastRepository: BroadcastNotificationRepository,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.broadcastRepository = broadcastRepository

    def perform(self, command: CreateBroadcastCommand) -> records.BroadcastNotification:
        _actorId, tenantId = _actor()
        # §12.38 idempotency — a redelivered event returns the existing row
        if command.idempotencyKey:
            existing = self.broadcastRepository.findByIdempotencyKey(
                tenantId, command.idempotencyKey
            )
            if existing is not None:
                return existing
        recipients = [asUuid(rid) for rid in command.recipientIds]
        notification = records.BroadcastNotification.create(
            tenantId=tenantId,
            notificationType=command.notificationType,
            title=command.title,
            body=command.body,
            recipientIds=recipients,
            now=self.clock.nowUtc(),
            priority=command.priority,
            severity=command.severity,
            sourceType=command.sourceType,
            sourceId=command.sourceId,
            deepLink=command.deepLink,
            language=command.language,
            metadata=dict(command.metadata),
            idempotencyKey=command.idempotencyKey,
            correlationId=command.correlationId,
        )
        self.broadcastRepository.save(notification)
        self.collectEventsFrom(notification)
        self.audit("CREATE", "Notification", str(notification.id), tenantId,
                  after={"type": command.notificationType,
                         "recipients": len(notification.recipients)})
        self.noteCreated(1)
        return notification


# ---------------------------------------------------------------------------
# Recipient read state (§12.8)
# ---------------------------------------------------------------------------


class RecipientStateService(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        broadcastRepository: BroadcastNotificationRepository,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.broadcastRepository = broadcastRepository

    def perform(self, command: RecipientStateCommand) -> records.NotificationRecipient:
        actorId, tenantId = _actor()
        recipient = self.broadcastRepository.getRecipient(
            tenantId, asUuid(command.notificationId), actorId
        )
        if recipient is None:
            raise EntityNotFoundError("NotificationRecipient", command.notificationId)
        now = self.clock.nowUtc()
        action = command.action
        if action == "read":
            recipient.markRead(now)
            eventName = "notificationRead"
        elif action == "unread":
            recipient.markUnread(now)
            eventName = "notificationMarkedUnread"
        elif action == "archive":
            recipient.archive(now)
            eventName = "notificationArchived"
        elif action == "dismiss":
            recipient.dismiss(now)
            eventName = "notificationDismissed"
        else:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError("unknown recipient action",
                                        fieldErrors={"action": action})
        self.broadcastRepository.saveRecipient(recipient)
        from apps.sharedKernel.domain.entities import DomainEvent

        self.eventDispatcher.dispatch(
            DomainEvent(
                name=eventName,
                occurredAt=now,
                tenantId=tenantId,
                actorId=actorId,
                payload={"notificationId": command.notificationId},
            )
        )
        self.audit(action.upper(), "NotificationRecipient", command.notificationId, tenantId)
        return recipient


# ---------------------------------------------------------------------------
# Queries / selectors (§12.43)
# ---------------------------------------------------------------------------


class BroadcastQueryService(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        broadcastRepository: BroadcastNotificationRepository,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.broadcastRepository = broadcastRepository

    def perform(self, command: Any) -> Any:
        actorId, tenantId = _actor()
        if isinstance(command, UnreadCountQuery):
            return {
                "unreadCount": self.broadcastRepository.unreadCount(tenantId, actorId)
            }
        if isinstance(command, ListBroadcastsQuery):
            notifications = self.broadcastRepository.listForRecipient(
                tenantId, actorId,
                unreadOnly=command.unreadOnly, limit=command.limit,
            )
            return [self._dto(n, actorId) for n in notifications]
        raise TypeError(f"unsupported query {type(command)}")

    def _dto(self, n: records.BroadcastNotification, viewerId: uuid.UUID) -> dict:
        recipient = n.recipientFor(viewerId)
        return {
            "id": str(n.id),
            "type": n.notificationType,
            "title": n.title,
            "body": n.body,
            "priority": n.priority,
            "severity": n.severity,
            "sourceType": n.sourceType,
            "sourceId": n.sourceId,
            "deepLink": n.deepLink,
            "state": recipient.state if recipient else "UNREAD",
            "readAt": recipient.readAt.isoformat() if recipient and recipient.readAt else None,
            "createdAt": n.createdAt.isoformat() if n.createdAt else None,
        }


# ---------------------------------------------------------------------------
# Delivery fan-out + retry (§12.14-§12.18)
# ---------------------------------------------------------------------------


class DeliveryDispatchService(NotificationUseCase):
    """Creates QUEUED deliveries for each (recipient × routed channel).

    Actual provider I/O happens in the worker (§12.40); this service only
    resolves channels from priority routing (§12.5) and persists QUEUED rows.
    """

    requiredAction = ""

    def __init__(
        self,
        broadcastRepository: BroadcastNotificationRepository,
        deliveryRepository: RecipientDeliveryRepository,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.broadcastRepository = broadcastRepository
        self.deliveryRepository = deliveryRepository

    def fanOut(self, notification: records.BroadcastNotification) -> list[records.RecipientDelivery]:
        channels = types.PRIORITY_CHANNEL_ROUTING.get(
            notification.priority, ("IN_APP",)
        )
        now = self.clock.nowUtc()
        created: list[records.RecipientDelivery] = []
        for recipient in notification.recipients:
            for channel in channels:
                delivery = records.RecipientDelivery.queue(
                    notification.tenantId, notification.id, recipient.userId, channel, now
                )
                self.deliveryRepository.save(delivery)
                self.collectEventsFrom(delivery)
                created.append(delivery)
        # realtime nudge for the in-app channel (§12.30)
        for recipient in notification.recipients:
            self.pushToUser(
                recipient.userId,
                {"type": "notification.created",
                 "notificationId": str(notification.id),
                 "title": notification.title},
            )
        return created


class DeliveryRetryService(NotificationUseCase):
    """Worker-side retry with exponential backoff and dead-letter (§12.17/§12.18)."""

    requiredAction = ""

    def __init__(
        self,
        deliveryRepository: RecipientDeliveryRepository,
        channelSender: Any = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.deliveryRepository = deliveryRepository
        self.channelSender = channelSender

    def retryPolicy(self) -> types.RetryPolicy:
        return types.RetryPolicy()

    def processDue(self, *, limit: int = 100) -> dict:
        now = self.clock.nowUtc()
        due = self.deliveryRepository.listRetryDue(now, limit=limit)
        processed = 0
        deadLettered = 0
        delivered = 0
        for delivery in due:
            outcome = self._attempt(delivery)
            processed += 1
            if outcome == "DEAD_LETTER":
                deadLettered += 1
            elif outcome == "DELIVERED":
                delivered += 1
        return {"processed": processed, "deadLettered": deadLettered,
                "delivered": delivered}

    def _attempt(self, delivery: records.RecipientDelivery) -> str:
        now = self.clock.nowUtc()
        try:
            delivery.markProcessing(now)
        except Exception:  # noqa: BLE001 — already processing/terminal: skip
            return "SKIPPED"
        policy = self.retryPolicy()
        # channelSender returns (succeeded, delivered, provider, msgId, errCode, errMsg)
        if self.channelSender is not None:
            succeeded, delivered, provider, msgId, errCode, errMsg = self.channelSender(delivery)
        else:
            # default: no transport configured — mark delivered for IN_APP only
            succeeded = delivered = delivery.channel == "IN_APP"
            provider, msgId, errCode, errMsg = "tekarai-inapp", "", "", ""
        attempt = delivery.recordAttempt(
            now,
            succeeded=succeeded,
            delivered=delivered,
            retryPolicy=policy,
            provider=provider,
            providerMessageId=msgId,
            errorCode=errCode,
            errorMessage=errMsg,
        )
        self.deliveryRepository.saveAttempt(attempt)
        self.deliveryRepository.save(delivery)
        self.collectEventsFrom(delivery)
        self.audit("ATTEMPT", "NotificationDelivery", str(delivery.id), delivery.tenantId,
                  after={"channel": delivery.channel, "status": delivery.status})
        if delivery.status == types.DLV_DELIVERED:
            self.noteDelivered()
            return "DELIVERED"
        if delivery.status == types.DLV_DEAD_LETTER:
            self.noteFailed()
            return "DEAD_LETTER"
        return "QUEUED"

    def perform(self, command: RetryDeliveryCommand) -> records.RecipientDelivery:
        _actorId, tenantId = _actor()
        delivery = self.deliveryRepository.getById(tenantId, asUuid(command.deliveryId))
        if delivery is None:
            raise EntityNotFoundError("NotificationDelivery", command.deliveryId)
        # manual ops retry: re-queue a dead-letter (§12.18)
        if delivery.status == types.DLV_DEAD_LETTER:
            delivery.status = types.DLV_QUEUED
            delivery.nextAttemptAt = self.clock.nowUtc()
            self.deliveryRepository.save(delivery)
        outcome = self._attempt(delivery)
        if outcome not in ("DELIVERED", "DEAD_LETTER"):
            pass
        return delivery


class DeliveryQueryService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        deliveryRepository: RecipientDeliveryRepository,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.deliveryRepository = deliveryRepository

    def perform(self, command: ListDeliveriesQuery) -> list[dict]:
        _actorId, tenantId = _actor()
        if command.deadLetterOnly:
            rows = self.deliveryRepository.listDeadLetter(tenantId, limit=command.limit)
        elif command.notificationId:
            rows = self.deliveryRepository.listForNotification(
                tenantId, asUuid(command.notificationId)
            )
        else:
            rows = self.deliveryRepository.listRetryDue(self.clock.nowUtc(), limit=command.limit)
        return [
            {
                "id": str(d.id),
                "notificationId": str(d.notificationId),
                "recipientId": str(d.recipientId),
                "channel": d.channel,
                "status": d.status,
                "attemptCount": d.attemptCount,
                "nextAttemptAt": d.nextAttemptAt.isoformat() if d.nextAttemptAt else None,
                "deliveredAt": d.deliveredAt.isoformat() if d.deliveredAt else None,
                "errorCode": d.errorCode,
            }
            for d in rows
        ]


# ---------------------------------------------------------------------------
# Rules (§12.24)
# ---------------------------------------------------------------------------


class RuleDefinitionService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        ruleRepository: NotificationRuleRepository,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.ruleRepository = ruleRepository

    def perform(self, command: DefineRuleCommand) -> records.NotificationRule:
        _actorId, tenantId = _actor()
        rule = records.NotificationRule.define(
            tenantId=tenantId,
            name=command.name,
            eventType=command.eventType,
            now=self.clock.nowUtc(),
            condition=dict(command.condition),
            recipientStrategy=command.recipientStrategy,
            channels=tuple(command.channels),
            priority=command.priority,
            templateKey=command.templateKey,
        )
        self.ruleRepository.save(rule)
        self.audit("CREATE", "NotificationRule", str(rule.id), tenantId,
                  after={"eventType": rule.eventType})
        return rule


# ---------------------------------------------------------------------------
# Event intake (§12.23/§12.38) — idempotent, rule-driven
# ---------------------------------------------------------------------------


class EventIntakeService(NotificationUseCase):
    def __init__(
        self,
        inboundEventRepository: InboundEventRepository,
        ruleRepository: NotificationRuleRepository,
        broadcastRepository: BroadcastNotificationRepository,
        dispatchService: DeliveryDispatchService | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.inboundEventRepository = inboundEventRepository
        self.ruleRepository = ruleRepository
        self.broadcastRepository = broadcastRepository
        self.dispatchService = dispatchService

    requiredAction = ""

    def perform(self, command: IngestEventCommand) -> list[records.BroadcastNotification]:
        _actorId, tenantId = _actor()
        # §12.38 idempotency — already processed event produces nothing new
        if self.inboundEventRepository.findProcessed(tenantId, command.eventId):
            return []
        event = records.InboundNotificationEvent.ingest(
            tenantId, command.eventId, command.eventType, self.clock.nowUtc(),
            payload=dict(command.payload),
        )
        self.inboundEventRepository.save(event)

        created: list[records.BroadcastNotification] = []
        rules = self.ruleRepository.listForEvent(tenantId, command.eventType)
        for rule in rules:
            if not rule.matches(command.eventType, command.payload):
                continue
            recipientIds = self._resolveRecipients(rule, command.payload)
            if not recipientIds:
                continue
            notification = records.BroadcastNotification.create(
                tenantId=tenantId,
                notificationType=command.eventType,
                title=str(command.payload.get("title", command.eventType)),
                body=str(command.payload.get("body", "")),
                recipientIds=recipientIds,
                now=self.clock.nowUtc(),
                priority=rule.priority,
                sourceType=str(command.payload.get("sourceType", "")),
                sourceId=str(command.payload.get("sourceId", "")),
                deepLink=str(command.payload.get("deepLink", "")),
                idempotencyKey=f"{command.eventId}:{rule.id}",
                correlationId=command.eventId,
            )
            self.broadcastRepository.save(notification)
            self.collectEventsFrom(notification)
            if self.dispatchService is not None:
                self.dispatchService.fanOut(notification)
            created.append(notification)

        event.markProcessed()
        self.inboundEventRepository.markProcessed(event)
        return created

    @staticmethod
    def _resolveRecipients(
        rule: records.NotificationRule, payload: dict
    ) -> list[uuid.UUID]:
        """§12.24 recipient strategy. TARGET uses explicit ids; other strategies
        read well-known payload keys populated by the emitting domain."""
        raw: Any
        if rule.recipientStrategy in ("TARGET", "ASSIGNEE"):
            raw = payload.get("recipientIds") or payload.get("assigneeId")
        elif rule.recipientStrategy == "MANAGER":
            raw = payload.get("managerId")
        elif rule.recipientStrategy == "ROLE":
            raw = payload.get("roleUserIds")
        else:
            raw = payload.get("recipientIds")
        if raw is None:
            return []
        if isinstance(raw, (list, tuple)):
            return [asUuid(x) for x in raw if x]
        return [asUuid(raw)]
