"""Communication application services — cross-context ports + shared base.

- ``UserDirectory``: lightweight identity lookups (user existence + username
  resolution) without coupling to the Identity context internals.
- ``CommunicationUseCase``: extends the kernel template with the §29 outbox
  (integration events written in the SAME transaction, published only after
  commit) and the §8 real-time broadcaster.
"""

from __future__ import annotations

import uuid
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.events import DomainEvent

TCommand = TypeVar("TCommand", bound=Any)
TResult = TypeVar("TResult")


@runtime_checkable
class UserDirectory(Protocol):
    """Identity lookups the communication context needs (§17/§3.7)."""

    def exists(self, tenantId: uuid.UUID, userId: uuid.UUID) -> bool: ...

    def usernameOf(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str: ...

    def idOfUsername(self, tenantId: uuid.UUID, username: str) -> uuid.UUID | None: ...


class CommunicationUseCase(UseCase[TCommand, TResult], Generic[TCommand, TResult]):
    """Kernel template + outbox (§29) + realtime broadcasts (§8).

    Integration events (``Communication…V1`` §25) are enqueued inside the
    transaction and dispatched only after commit — never before the data is
    safely stored (§28).
    """

    def __init__(
        self,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
        outboxRepository: Any,
        realtime: Any,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.outboxRepository = outboxRepository
        self.realtime = realtime
        self._sendStartedAt = 0.0

    # -- §39 metrics hooks (no payload data ever recorded) ---------------------

    def noteSendStarted(self) -> None:
        import time

        self._sendStartedAt = time.monotonic()

    def noteSendDelivered(self) -> None:
        from apps.communication.infrastructure.metrics.communicationMetrics import (
            communicationMetrics,
        )

        communicationMetrics().increment("messagesSent")
        if self._sendStartedAt:
            communicationMetrics().observeMessageDelivery(self._sendStartedAt)
            self._sendStartedAt = 0.0

    def noteSignalingFailure(self) -> None:
        from apps.communication.infrastructure.metrics.communicationMetrics import (
            communicationMetrics,
        )

        communicationMetrics().increment("failedSignalingRequests")

    # -- §25/§29 ------------------------------------------------------------------

    def emitIntegrationEvent(
        self, tenantId: uuid.UUID, domainEventName: str, payload: dict[str, Any]
    ) -> None:
        """Queue ``Communication<Name>V1`` for post-commit publication."""
        integrationName = f"Communication{domainEventName}V1"
        self.outboxRepository.enqueue(
            tenantId=tenantId,
            eventType=integrationName,
            payload=payload,
            occurredAt=self.clock.nowUtc(),
        )

    def broadcastConversation(self, conversationId: uuid.UUID, event: dict[str, Any]) -> None:
        self.realtime.toConversation(conversationId, event)

    def broadcastUser(self, userId: uuid.UUID, event: dict[str, Any]) -> None:
        self.realtime.toUser(userId, event)

    def broadcastCall(self, callId: uuid.UUID, event: dict[str, Any]) -> None:
        self.realtime.toCall(callId, event)

    def broadcastMeeting(self, meetingId: uuid.UUID, event: dict[str, Any]) -> None:
        self.realtime.toMeeting(meetingId, event)

    def publishPendingEvents(self) -> None:
        """Kernel step 6 extended: after domain events, flush the outbox
        (§29) so external consumers (notify/AI/Analytics) never lose
        an event that was committed."""
        super().publishPendingEvents()
        self.dispatchOutbox()

    def dispatchOutbox(self) -> None:
        for row in self.outboxRepository.pending():
            try:
                self.eventDispatcher.dispatch(
                    DomainEvent(
                        name=row.eventType,
                        occurredAt=row.occurredAt,
                        tenantId=row.tenantId,
                        payload=row.payload,
                    )
                )
                self.outboxRepository.markPublished(row.id, self.clock.nowUtc())
                self._metrics().increment("outboxEventsPublished")
            except Exception:  # noqa: BLE001 — §38 event delivery failure: row stays pending
                continue

    @staticmethod
    def _metrics():
        from apps.communication.infrastructure.metrics.communicationMetrics import (
            communicationMetrics,
        )

        return communicationMetrics()
