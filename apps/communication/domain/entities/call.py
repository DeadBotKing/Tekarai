"""Call + CallParticipant aggregates (Phase 08 §10–§12).

WebRTC carries the media; the backend owns call sessions, signaling relay,
participant state and audit (§10). Calls may attach to a conversation
(direct/group call) or a meeting (group/SFU mode, §12).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.communication.domain.valueObjects.communicationTypes import (
    CALL_ACTIVE,
    CALL_CANCELLED,
    CALL_ENDED,
    CALL_MISSED,
    CALL_REJECTED,
    CALL_RINGING,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError

CALL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    CALL_RINGING: (CALL_ACTIVE, CALL_ENDED, CALL_REJECTED, CALL_MISSED, CALL_CANCELLED),
    CALL_ACTIVE: (CALL_ENDED,),
    CALL_ENDED: (),
    CALL_REJECTED: (),
    CALL_MISSED: (),
    CALL_CANCELLED: (),
}


class Call(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        initiatorId: uuid.UUID,
        mediaType: str,
        createdAt: datetime,
        *,
        conversationId: uuid.UUID | None = None,
        meetingId: uuid.UUID | None = None,
        callStatus: str = CALL_RINGING,
        startedAt: datetime | None = None,
        endedAt: datetime | None = None,
        clientRequestId: str = "",
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.initiatorId = initiatorId
        self.mediaType = mediaType
        self.createdAt = createdAt
        self.conversationId = conversationId
        self.meetingId = meetingId
        self.callStatus = callStatus
        self.startedAt = startedAt
        self.endedAt = endedAt
        self.clientRequestId = clientRequestId

    # -- factories ---------------------------------------------------------------

    @staticmethod
    def start(
        tenantId: uuid.UUID,
        initiatorId: uuid.UUID,
        mediaType: str,
        now: datetime,
        *,
        conversationId: uuid.UUID | None = None,
        meetingId: uuid.UUID | None = None,
        clientRequestId: str = "",
    ) -> Call:
        if conversationId is None and meetingId is None:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "A call must attach to a conversation or a meeting.",
                fieldErrors={"target": "missing"},
            )
        call = Call(
            id=newId(),
            tenantId=tenantId,
            initiatorId=initiatorId,
            mediaType=mediaType,
            createdAt=now,
            conversationId=conversationId,
            meetingId=meetingId,
            clientRequestId=clientRequestId,
        )
        call.recordEvent(
            DomainEvent(
                name="callStarted",
                occurredAt=now,
                tenantId=tenantId,
                actorId=initiatorId,
                payload={"mediaType": mediaType},
            )
        )
        return call

    # -- lifecycle (§10) -----------------------------------------------------------

    def transitionTo(self, target: str, now: datetime) -> None:
        allowed = CALL_TRANSITIONS.get(self.callStatus, ())
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"Call cannot move {self.callStatus} → {target}."
            )
        self.callStatus = target
        if target == CALL_ACTIVE:
            self.startedAt = now
            self.recordEvent(
                DomainEvent(name="callAccepted", occurredAt=now, tenantId=self.tenantId)
            )
        elif target in (CALL_ENDED, CALL_REJECTED, CALL_MISSED, CALL_CANCELLED):
            self.endedAt = now
            self.recordEvent(
                DomainEvent(
                    name="callRejected" if target == CALL_REJECTED else "callEnded",
                    occurredAt=now,
                    tenantId=self.tenantId,
                    payload={"finalState": target},
                )
            )

    def accept(self, now: datetime) -> None:
        self.transitionTo(CALL_ACTIVE, now)

    def reject(self, now: datetime) -> None:
        self.transitionTo(CALL_REJECTED, now)

    def end(self, now: datetime) -> None:
        if self.callStatus == CALL_RINGING:
            # nobody answered → the initiator hanging up is a cancel/miss
            self.transitionTo(CALL_CANCELLED, now)
        else:
            self.transitionTo(CALL_ENDED, now)

    def isRinging(self) -> bool:
        return self.callStatus == CALL_RINGING

    def isActive(self) -> bool:
        return self.callStatus == CALL_ACTIVE

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "status": self.callStatus,
            "mediaType": self.mediaType,
            "initiatorId": str(self.initiatorId),
        }


class CallParticipant(AggregateRoot):
    """One leg of a call: joined/left times + media state (§10/§14)."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        callId: uuid.UUID,
        userId: uuid.UUID,
        joinedAt: datetime,
        *,
        leftAt: datetime | None = None,
        mediaState: str = "connected",
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.callId = callId
        self.userId = userId
        self.joinedAt = joinedAt
        self.leftAt = leftAt
        self.mediaState = mediaState

    @staticmethod
    def join(
        tenantId: uuid.UUID, callId: uuid.UUID, userId: uuid.UUID, now: datetime
    ) -> CallParticipant:
        return CallParticipant(
            id=newId(), tenantId=tenantId, callId=callId, userId=userId, joinedAt=now
        )

    def leave(self, now: datetime) -> None:
        if self.leftAt is not None:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Already left the call.")
        self.leftAt = now

    def setMediaState(self, state: str) -> None:
        """§14 MEDIA_STATE_CHANGE — e.g. screen sharing on/off, muted."""
        if not state.strip():
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError("Empty media state.")
        self.mediaState = state.strip()

    def isActive(self) -> bool:
        return self.leftAt is None

    def snapshot(self) -> dict[str, Any]:
        return {
            "callId": str(self.callId),
            "userId": str(self.userId),
            "mediaState": self.mediaState,
            "active": self.isActive(),
        }
