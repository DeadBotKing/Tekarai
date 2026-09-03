"""§26/§40 receipt services — read ≠ acknowledged; archive is soft delete."""

from __future__ import annotations

import uuid
from typing import Any

from apps.notifications.application.commands.notificationCommands import (
    AcknowledgeNotificationCommand,
    ArchiveNotificationCommand,
    MarkNotificationReadCommand,
    MarkNotificationsReadCommand,
    MarkNotificationUnreadCommand,
)
from apps.notifications.application.dto.notificationDtos import (
    NotificationDto,
    NotificationPageDto,
    notificationDtoFromDomain,
)
from apps.notifications.application.queries.notificationQueries import (
    GetNotificationQuery,
    ListNotificationsQuery,
    UnreadCountQuery,
)
from apps.notifications.application.services.notificationSupport import (
    NotificationUseCase,
)
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationDeliveryRepository,
    NotificationRepository,
)
from apps.sharedKernel.domain.errors import EntityNotFoundError, PermissionDeniedError


def _loadOwned(
    repository: NotificationRepository,
    notificationId: uuid.UUID | str,
    recipientId: uuid.UUID,
) -> Any:
    notification = repository.getById(notificationId)
    if notification is None or notification.deletedAt is not None:
        raise EntityNotFoundError("NotificationRecord", str(notificationId))
    if notification.recipientId != recipientId:
        # §34 — never leak cross-recipient existence
        raise EntityNotFoundError("NotificationRecord", str(notificationId))
    return notification


class MarkNotificationReadService(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository

    def perform(self, command: MarkNotificationReadCommand | MarkNotificationsReadCommand) -> dict:
        now = self.nowUtc()
        if isinstance(command, MarkNotificationsReadCommand):
            count = 0
            for notificationId in command.notificationIds:
                notification = _loadOwned(
                    self.notificationRepository, notificationId, command.recipientId
                )
                notification.markRead(now)
                self.notificationRepository.update(notification)
                self.collectEventsFrom(notification)
                count += 1
            return {"markedRead": count}
        notification = _loadOwned(
            self.notificationRepository, command.notificationId, command.recipientId
        )
        notification.markRead(now)
        self.notificationRepository.update(notification)
        self.collectEventsFrom(notification)
        self.audit(
            "UPDATE",
            resourceType="NotificationRecord",
            resourceId=str(notification.id),
            tenantId=notification.tenantId,
            after={"readAt": now.isoformat()},
        )
        self.pushToUser(
            notification.recipientId,
            {
                "name": "notificationRead",
                "notificationId": str(notification.id),
            },
        )
        return {"markedRead": 1}


class MarkNotificationUnreadService(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository

    def perform(self, command: MarkNotificationUnreadCommand) -> dict:
        notification = _loadOwned(
            self.notificationRepository, command.notificationId, command.recipientId
        )
        notification.markUnread(self.nowUtc())
        self.notificationRepository.update(notification)
        self.collectEventsFrom(notification)
        return {"markedUnread": 1}


class AcknowledgeNotificationService(NotificationUseCase):
    """§26 — acknowledgement is a deliberate act, never implicit on read."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository

    def perform(self, command: AcknowledgeNotificationCommand) -> dict:
        notification = _loadOwned(
            self.notificationRepository, command.notificationId, command.recipientId
        )
        if not notification.requiresAcknowledgement and notification.acknowledgedAt is None:
            raise PermissionDeniedError(
                "This notification does not require acknowledgement.",
                action="notification.acknowledge",
            )
        notification.acknowledge(self.nowUtc(), command.recipientId)
        self.notificationRepository.update(notification)
        self.collectEventsFrom(notification)
        self.audit(
            "APPROVAL",
            resourceType="NotificationRecord",
            resourceId=str(notification.id),
            tenantId=notification.tenantId,
            after={"acknowledgedAt": notification.acknowledgedAt.isoformat()},
        )
        return {"acknowledged": True}


class ArchiveNotificationService(NotificationUseCase):
    """§40 'Delete/Archive where allowed' — soft delete, restorable by admin."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository

    def perform(self, command: ArchiveNotificationCommand) -> dict:
        notification = _loadOwned(
            self.notificationRepository, command.notificationId, command.recipientId
        )
        notification.archive(self.nowUtc())
        self.notificationRepository.update(notification)
        self.collectEventsFrom(notification)
        return {"archived": True}


class ListNotificationsUseCase(NotificationUseCase):
    """§40 list + §42 recovery read — DB is the source of truth."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        deliveryRepository: NotificationDeliveryRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository
        self.deliveryRepository = deliveryRepository

    def perform(self, query: ListNotificationsQuery) -> NotificationPageDto:
        notifications, unreadCount, hasNext = self.notificationRepository.listForRecipient(
            query.tenantId,
            query.recipientId,
            unreadOnly=query.unreadOnly,
            category=query.category,
            priority=query.priority,
            beforeId=query.beforeId,
            limit=query.limit,
            includeArchived=query.includeArchived,
        )
        items = [
            notificationDtoFromDomain(
                notification,
                self.deliveryRepository.getForNotification(notification.id),
            )
            for notification in notifications
        ]
        return NotificationPageDto(
            items=items, unreadCount=unreadCount, hasNext=hasNext
        )


class GetNotificationUseCase(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        deliveryRepository: NotificationDeliveryRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository
        self.deliveryRepository = deliveryRepository

    def perform(self, query: GetNotificationQuery) -> NotificationDto:
        notification = _loadOwned(
            self.notificationRepository, query.notificationId, query.recipientId
        )
        deliveries = self.deliveryRepository.getForNotification(notification.id)
        return notificationDtoFromDomain(notification, deliveries)


class UnreadCountUseCase(NotificationUseCase):
    """§37 unread badge query — recipientId+readAt+createdAt index."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository

    def perform(self, query: UnreadCountQuery) -> dict:
        return {"unreadCount": self.notificationRepository.unreadCount(
            query.tenantId, query.recipientId
        )}
