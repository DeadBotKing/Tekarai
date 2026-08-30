"""Notification application support — shared base + context ports.

- ``NotificationUseCase``: kernel template extended with the realtime port
  (§41) and metrics hooks (§44).
- ``NotificationChannelRegistry`` / ``NotificationJobQueue``: replaceable
  infrastructure seams (§13 providers, §31 broker) — the application layer
  depends on these Protocols only.
- ``AiNotificationComposer``: §43 — AI may compose notifications, but only
  through this port (the future AI engine plugs in here).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationChannelPort,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import UseCase

logger = logging.getLogger(__name__)


@runtime_checkable
class NotificationChannelRegistry(Protocol):
    """§12/§13 — channel adapters live in infrastructure; services look
    them up by name and never import providers directly."""

    def channelFor(self, channel: str) -> NotificationChannelPort | None: ...

    def availableChannels(self) -> list[str]: ...


@runtime_checkable
class NotificationJobQueue(Protocol):
    """§31 — async processing seam. The default implementation runs the
    worker inline after commit; a broker-backed implementation (Celery,
    RQ, …) can replace it without touching application code."""

    def submit(self, job: dict[str, Any]) -> None: ...


@runtime_checkable
class AiNotificationComposer(Protocol):
    """§43 — optional AI composition interface (engine-side only)."""

    def compose(self, *, tenantId: Any, prompt: str, context: dict[str, Any]) -> dict[str, Any]: ...


class NotificationUseCase(UseCase):
    """Kernel eight-step template + realtime + metrics (§41/§44)."""

    def __init__(
        self,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
        realtime: Any,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.realtime = realtime

    # -- §41 realtime optimization (DB stays the source of truth §42) ---------

    def pushToUser(self, userId: Any, event: dict[str, Any]) -> None:
        try:
            self.realtime.toUser(userId, event)
        except Exception:  # noqa: BLE001 — realtime must never break delivery
            logger.exception("Realtime push failed", extra={"userId": str(userId)})

    # -- §44 metric hooks ------------------------------------------------------

    def noteCreated(self, amount: int = 1) -> None:
        from apps.notifications.infrastructure.metrics.notificationMetrics import (
            notificationMetrics,
        )

        notificationMetrics().increment("notificationsCreated", amount)

    def noteDelivered(self) -> None:
        from apps.notifications.infrastructure.metrics.notificationMetrics import (
            notificationMetrics,
        )

        notificationMetrics().increment("notificationsDelivered")

    def noteFailed(self) -> None:
        from apps.notifications.infrastructure.metrics.notificationMetrics import (
            notificationMetrics,
        )

        notificationMetrics().increment("notificationsFailed")
