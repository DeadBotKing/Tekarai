"""§38 CreateNotificationService — the notification entry point.

Implements §7 (event-driven input), §9 (recipient fan-out), §28
(anti-storm: cooldown + window + digest aggregation), §29 (hashed
idempotency key) and §23 (expiry). Channel execution itself is §32 and
lives in DispatchNotificationService.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from apps.notifications.application.commands.notificationCommands import (
    CreateNotificationCommand,
)
from apps.notifications.application.dto.notificationDtos import (
    NotificationDto,
    notificationDtoFromDomain,
)
from apps.notifications.application.services.notificationSupport import (
    NotificationJobQueue,
    NotificationUseCase,
)
from apps.notifications.application.services.resolvePolicyAndPreferences import (
    ResolveNotificationPolicyService,
)
from apps.notifications.application.services.resolveRecipients import (
    ResolveRecipientsService,
    ResolvedRecipient,
)
from apps.notifications.domain.entities.notification import Notification
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationDigestRepository,
    NotificationRepository,
)
from apps.notifications.domain.services import notificationRules
from apps.notifications.domain.valueObjects.notificationTypes import (
    CHANNEL_IN_APP,
    DELIVERY_CHANNELS,
    NOTIFICATION_CATEGORIES,
    NOTIFICATION_PRIORITIES,
    RATE_WINDOW_SECONDS,
    idempotencyKeyOf,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

logger = logging.getLogger(__name__)


@dataclass
class CreationOutcome:
    """Mutable accumulator — services tally per-recipient outcomes."""

    notifications: list[NotificationDto] = field(default_factory=list)
    duplicates: int = 0
    aggregatedToDigest: int = 0
    skippedRecipients: int = 0


class CreateNotificationService(NotificationUseCase):
    """Creates one single-recipient aggregate per resolved recipient."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        digestRepository: NotificationDigestRepository,
        resolveRecipients: ResolveRecipientsService,
        resolvePolicy: ResolveNotificationPolicyService,
        renderService: Any,
        jobQueue: NotificationJobQueue,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository
        self.digestRepository = digestRepository
        self.resolveRecipients = resolveRecipients
        self.resolvePolicy = resolvePolicy
        self.renderService = renderService
        self.jobQueue = jobQueue
        self._pendingJobs: list[dict[str, Any]] = []

    # -- step 1: input validation ------------------------------------------------

    def validateCommand(self, message: CreateNotificationCommand) -> None:
        if message.category not in NOTIFICATION_CATEGORIES:
            raise ValidationFailedError(
                "Unknown notification category.", fieldErrors={"category": message.category}
            )
        if message.priority not in NOTIFICATION_PRIORITIES:
            raise ValidationFailedError(
                "Unknown priority.", fieldErrors={"priority": message.priority}
            )
        unknown = [c for c in message.channels if c not in DELIVERY_CHANNELS]
        if unknown:
            raise ValidationFailedError(
                "Unknown channel override.", fieldErrors={"channels": str(unknown)}
            )
        if not message.title.strip():
            raise ValidationFailedError(
                "Title is required.", fieldErrors={"title": "empty"}
            )
        if not str(message.eventId).strip():
            raise ValidationFailedError(
                "eventId is required for deduplication.", fieldErrors={"eventId": "empty"}
            )

    def perform(self, command: CreateNotificationCommand) -> CreationOutcome:
        now = self.nowUtc()
        recipients = self.resolveRecipients.resolve(command.tenantId, command.recipientSpec)
        policyResolution = self.resolvePolicy.resolve(
            command.tenantId, command.notificationType, command.category
        )
        policy = policyResolution.policy

        outcome = CreationOutcome()
        for recipient in recipients:
            idempotencyKey = idempotencyKeyOf(
                tenantId=command.tenantId,
                eventType=command.eventType,
                eventId=command.eventId,
                recipientId=str(recipient.userId),
                notificationType=command.notificationType,
            )
            existing = self.notificationRepository.findByIdempotencyKey(
                command.tenantId, idempotencyKey
            )
            if existing is not None:
                outcome.duplicates += 1  # §29 duplicate event/notification
                outcome.notifications.append(notificationDtoFromDomain(existing))
                continue

            storm = self._stormControl(
                command, recipient, policy.cooldownSeconds, now
            )

            payload = dict(command.data)
            if recipient.externalAddress:
                payload["externalAddress"] = recipient.externalAddress
            payload["resolutionTrace"] = policyResolution.trace()

            notification = Notification(
                id=self.newId(),
                tenantId=command.tenantId,
                recipientId=recipient.userId,
                notificationType=command.notificationType,
                category=command.category,
                title=command.title,
                body=command.body,
                priority=command.priority,
                sourceType=command.sourceType,
                sourceId=command.sourceId,
                createdAt=now,
                expiresAt=command.expiresAt,
                idempotencyKey=idempotencyKey,
                requiresAcknowledgement=command.ackRequired,
                correlationId=command.correlationId,
                causationId=command.causationId or command.eventType,
                payload=payload,
            )
            notification.language = self._languageOf(command, recipient.userId)
            if storm is not None:
                notification.payload["rateLimit"] = storm
                notification.payload["channelsOverride"] = [CHANNEL_IN_APP]

            self.notificationRepository.create(notification)
            self.collectEventsFrom(notification)
            self.audit(
                "CREATE",
                resourceType="NotificationRecord",
                resourceId=str(notification.id),
                tenantId=command.tenantId,
                after={"notificationType": notification.notificationType,
                       "category": notification.category},
            )
            self.noteCreated()

            if storm is not None and policy.digestible:
                self._addToDigest(command, notification, now)
                outcome.aggregatedToDigest += 1

            outcome.notifications.append(notificationDtoFromDomain(notification))
            self._enqueueDispatch(notification)

        if not recipients:
            outcome.skippedRecipients = 1
        return outcome

    # -- §28 anti-storm -----------------------------------------------------------

    def _stormControl(
        self,
        command: CreateNotificationCommand,
        recipient: ResolvedRecipient,
        cooldownSeconds: int,
        now: Any,
    ) -> str | None:
        """Returns the applied strategy or None when delivery is normal."""
        lastCreatedAt = self.notificationRepository.lastCreatedAtOfType(
            command.tenantId, recipient.userId, command.notificationType
        )
        if lastCreatedAt is not None and notificationRules.withinCooldown(
            lastCreatedAt, now, max(cooldownSeconds, 0)
        ):
            return "cooldown"

        recentCount = self.notificationRepository.countRecentOfType(
            command.tenantId,
            recipient.userId,
            command.notificationType,
            self._since(now),
        )
        if notificationRules.exceedsRateWindow(recentCount):
            return "rateWindow"
        return None

    @staticmethod
    def _since(now: Any):
        from datetime import timedelta

        return now - timedelta(seconds=RATE_WINDOW_SECONDS)

    def _languageOf(self, command: CreateNotificationCommand, userId: uuid.UUID) -> str:
        return self.renderService.resolveLanguageFor(command.tenantId, userId)

    def _addToDigest(
        self, command: CreateNotificationCommand, notification: Notification, now: Any
    ) -> None:
        from apps.notifications.application.services.digestServices import (
            CreateDigestService,
        )
        from apps.notifications.infrastructure.container import container

        createDigest: CreateDigestService = container.createDigestService()
        createDigest.addItemFor(
            tenantId=command.tenantId,
            userId=notification.recipientId,
            notificationId=notification.id,
            now=now,
        )

    def _enqueueDispatch(self, notification: Notification) -> None:
        """§31 — hand the job to the queue port AFTER commit (see execute())."""
        self._pendingJobs.append(
            {
                "kind": "DISPATCH",
                "tenantId": str(notification.tenantId),
                "notificationId": str(notification.id),
                "idempotencyKey": notification.idempotencyKey,
            }
        )

    def execute(self, message: CreateNotificationCommand) -> CreationOutcome:
        self._pendingJobs = []
        outcome = super().execute(message)
        # §7/§31 — external delivery starts only after the row is committed
        for job in self._pendingJobs:
            self.jobQueue.submit(job)
        self._pendingJobs = []
        return outcome

    @staticmethod
    def newId() -> uuid.UUID:
        from apps.sharedKernel.domain.entities import newId

        return newId()
