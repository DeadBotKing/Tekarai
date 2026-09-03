"""Phase 11 repository ports (interfaces).

The domain/application layers depend on these Protocols only; the Django
implementations live in infrastructure (§47/§54). Every method takes an explicit
``tenantId`` so cross-tenant queries are impossible (§4).
"""

from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from apps.communication.domain.entities.phase11Records import (
    ActionItemCandidate,
    CommunicationPolicy,
    LegalHold,
    MeetingRoom,
    MeetingSession,
    MeetingSummary,
    MessageDelivery,
    MessageReport,
    OfficialMessage,
    ScreenShareSession,
)


@runtime_checkable
class CommunicationPolicyRepository(Protocol):
    def getForTenant(self, tenantId: uuid.UUID) -> CommunicationPolicy | None: ...
    def save(self, policy: CommunicationPolicy) -> None:
        """Upsert the single active policy row for the tenant."""


@runtime_checkable
class MessageDeliveryRepository(Protocol):
    def get(
        self, tenantId: uuid.UUID, messageId: uuid.UUID, recipientId: uuid.UUID
    ) -> MessageDelivery | None: ...
    def save(self, delivery: MessageDelivery) -> None: ...
    def listForMessage(
        self, tenantId: uuid.UUID, messageId: uuid.UUID
    ) -> list[MessageDelivery]: ...


@runtime_checkable
class MeetingRoomRepository(Protocol):
    def findByMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> MeetingRoom | None: ...
    def getById(
        self, tenantId: uuid.UUID, roomId: uuid.UUID
    ) -> MeetingRoom | None: ...
    def save(self, room: MeetingRoom) -> None: ...
    def saveSession(self, session: MeetingSession) -> None: ...
    def listSessions(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> list[MeetingSession]: ...


@runtime_checkable
class ScreenShareRepository(Protocol):
    def activeForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> list[ScreenShareSession]: ...
    def save(self, share: ScreenShareSession) -> None: ...


@runtime_checkable
class MeetingSummaryRepository(Protocol):
    def findForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> MeetingSummary | None: ...
    def getById(
        self, tenantId: uuid.UUID, summaryId: uuid.UUID
    ) -> MeetingSummary | None: ...
    def save(self, summary: MeetingSummary) -> None: ...


@runtime_checkable
class ActionItemRepository(Protocol):
    def save(self, item: ActionItemCandidate) -> None: ...
    def getById(
        self, tenantId: uuid.UUID, itemId: uuid.UUID
    ) -> ActionItemCandidate | None: ...
    def listForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> list[ActionItemCandidate]: ...
    def listPending(
        self, tenantId: uuid.UUID, *, limit: int = 50
    ) -> list[ActionItemCandidate]: ...


@runtime_checkable
class OfficialMessageRepository(Protocol):
    def save(self, message: OfficialMessage) -> None: ...
    def getById(
        self, tenantId: uuid.UUID, officialId: uuid.UUID
    ) -> OfficialMessage | None: ...
    def list(
        self,
        tenantId: uuid.UUID,
        *,
        status: str = "",
        limit: int = 50,
    ) -> list[OfficialMessage]: ...


@runtime_checkable
class MessageReportRepository(Protocol):
    def save(self, report: MessageReport) -> None: ...
    def getById(
        self, tenantId: uuid.UUID, reportId: uuid.UUID
    ) -> MessageReport | None: ...
    def list(
        self, tenantId: uuid.UUID, *, status: str = "", limit: int = 50
    ) -> list[MessageReport]: ...


@runtime_checkable
class LegalHoldRepository(Protocol):
    def save(self, hold: LegalHold) -> None: ...
    def activeFor(
        self, tenantId: uuid.UUID, scope: str, targetId: uuid.UUID
    ) -> LegalHold | None: ...
    def listActiveForTarget(
        self, tenantId: uuid.UUID, targetId: uuid.UUID
    ) -> list[LegalHold]: ...
