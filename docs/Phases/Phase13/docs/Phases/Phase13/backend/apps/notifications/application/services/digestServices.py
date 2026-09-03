"""§21 digest services — create + send."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from apps.notifications.application.commands.notificationCommands import (
    SendDueDigestsCommand,
)
from apps.notifications.application.dto.notificationDtos import digestDtoFromDomain
from apps.notifications.application.services.notificationSupport import (
    NotificationUseCase,
)
from apps.notifications.domain.entities.notificationDigest import NotificationDigest
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationDigestRepository,
    NotificationRepository,
)
from apps.notifications.domain.valueObjects.notificationTypes import (
    DIGEST_DAILY,
    DIGEST_HOURLY,
    DIGEST_STATUS_OPEN,
    DIGEST_WEEKLY,
)

_PERIOD_SECONDS = {DIGEST_HOURLY: 3600, DIGEST_DAILY: 86400, DIGEST_WEEKLY: 604800}


class CreateDigestService(NotificationUseCase):
    """§21/§28 — aggregates notification storms into one open digest."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        digestRepository: NotificationDigestRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.digestRepository = digestRepository

    def perform(self, message: Any) -> Any:  # pragma: no cover — see addItemFor
        raise NotImplementedError

    def addItemFor(
        self,
        *,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        notificationId: uuid.UUID,
        now: Any,
        kind: str = DIGEST_HOURLY,
    ) -> NotificationDigest:
        digest = self.digestRepository.openDigest(tenantId, userId, kind)
        if digest is None:
            window = _PERIOD_SECONDS.get(kind, 3600)
            digest = NotificationDigest(
                id=uuid.uuid4(),
                tenantId=tenantId,
                userId=userId,
                kind=kind,
                periodStart=now,
                periodEnd=now + timedelta(seconds=window),
            )
            self.digestRepository.create(digest)
        digest.addItem()
        self.digestRepository.update(digest)
        self.digestRepository.addItem(digest.id, notificationId)
        return digest


class SendDigestService(NotificationUseCase):
    """§21 — when the period elapses, one summary notification per user."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        digestRepository: NotificationDigestRepository,
        notificationRepository: NotificationRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.digestRepository = digestRepository
        self.notificationRepository = notificationRepository

    def perform(self, command: SendDueDigestsCommand) -> dict:
        from apps.notifications.application.commands.notificationCommands import (
            CreateNotificationCommand,
        )
        from apps.notifications.application.services.createNotification import (
            CreateNotificationService,
        )
        from apps.notifications.infrastructure.container import container

        now = self.nowUtc()
        sent = 0
        createService: CreateNotificationService = container.createNotificationService()
        for digest in self._dueDigests(command.kind, now):
            items = self.digestRepository.itemsOf(digest.id)
            if not items:
                digest.markSent(now)
                self.digestRepository.update(digest)
                continue
            outcome = createService.execute(
                CreateNotificationCommand(
                    tenantId=digest.tenantId,
                    recipientSpec={"type": "USER", "value": str(digest.userId)},
                    eventType="digest.due",
                    eventId=f"digest:{digest.id}",
                    notificationType="digest.summary",
                    category="SYSTEM",
                    priority="LOW",
                    title="You have new notifications",
                    body=f"{digest.itemCount} notifications were grouped into this digest.",
                    sourceType="DIGEST",
                    sourceId=str(digest.id),
                    data={"digestId": str(digest.id), "itemCount": digest.itemCount},
                    correlationId=f"digest:{digest.id}",
                    causationId=f"digest:{digest.id}",
                )
            )
            if outcome.notifications:
                sent += 1
            digest.markSent(now)
            self.digestRepository.update(digest)
        return {"digestsSent": sent}

    def _dueDigests(self, kind: str, now: Any) -> list[NotificationDigest]:
        from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
            dueOpenDigests,
        )

        return dueOpenDigests(kind, now)
