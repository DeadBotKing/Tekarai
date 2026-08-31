"""Meeting + MeetingParticipant aggregates (Phase 08 §13).

Meeting state machine: SCHEDULED→(WAITING|LIVE|CANCELLED), WAITING→(LIVE|
CANCELLED), LIVE→ENDED; ENDED/CANCELLED terminal. Participants move through
INVITED→ACCEPTED/DECLINED→JOINED→LEFT (§13).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.communication.domain.valueObjects.communicationTypes import (
    MEETING_ACCEPTED,
    MEETING_DECLINED,
    MEETING_INVITED,
    MEETING_JOINED,
    MEETING_LEFT,
    MEETING_LIVE,
    MEETING_SCHEDULED,
    MEETING_TRANSITIONS,
    MEETING_WAITING,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError


class Meeting(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        organizerId: uuid.UUID,
        title: str,
        createdAt: datetime,
        *,
        description: str = "",
        scheduledStart: datetime | None = None,
        scheduledEnd: datetime | None = None,
        actualStart: datetime | None = None,
        actualEnd: datetime | None = None,
        meetingStatus: str = MEETING_SCHEDULED,
        clientRequestId: str = "",
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.conversationId = conversationId
        self.organizerId = organizerId
        self.title = title.strip()
        self.description = description.strip()
        self.createdAt = createdAt
        self.scheduledStart = scheduledStart
        self.scheduledEnd = scheduledEnd
        self.actualStart = actualStart
        self.actualEnd = actualEnd
        self.meetingStatus = meetingStatus
        self.clientRequestId = clientRequestId

    # -- factory -----------------------------------------------------------------

    @staticmethod
    def schedule(
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        organizerId: uuid.UUID,
        title: str,
        now: datetime,
        *,
        description: str = "",
        scheduledStart: datetime | None = None,
        scheduledEnd: datetime | None = None,
    ) -> Meeting:
        if not title.strip():
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Meeting title is required.", fieldErrors={"title": "empty"}
            )
        meeting = Meeting(
            id=newId(),
            tenantId=tenantId,
            conversationId=conversationId,
            organizerId=organizerId,
            title=title,
            createdAt=now,
            description=description,
            scheduledStart=scheduledStart,
            scheduledEnd=scheduledEnd,
        )
        meeting.recordEvent(
            DomainEvent(
                name="meetingCreated",
                occurredAt=now,
                tenantId=tenantId,
                actorId=organizerId,
                payload={"title": meeting.title},
            )
        )
        return meeting

    # -- lifecycle (§13) -----------------------------------------------------------

    def transitionTo(self, target: str, now: datetime) -> None:
        allowed = MEETING_TRANSITIONS.get(self.meetingStatus, ())
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"Meeting cannot move {self.meetingStatus} → {target}."
            )
        self.meetingStatus = target
        if target == MEETING_LIVE:
            self.actualStart = now
            self.recordEvent(
                DomainEvent(name="meetingStarted", occurredAt=now, tenantId=self.tenantId)
            )
        elif target == MEETING_WAITING:
            self.recordEvent(
                DomainEvent(name="meetingWaiting", occurredAt=now, tenantId=self.tenantId)
            )
        elif target in ("ENDED", "CANCELLED"):
            self.actualEnd = now
            self.recordEvent(
                DomainEvent(
                    name="meetingEnded" if target == "ENDED" else "meetingCancelled",
                    occurredAt=now,
                    tenantId=self.tenantId,
                )
            )

    def start(self, now: datetime) -> None:
        if self.meetingStatus == MEETING_WAITING:
            self.transitionTo(MEETING_LIVE, now)
        else:
            self.transitionTo(MEETING_LIVE, now)  # SCHEDULED → LIVE also legal

    def isLive(self) -> bool:
        return self.meetingStatus == MEETING_LIVE

    def isJoinable(self) -> bool:
        return self.meetingStatus in (MEETING_WAITING, MEETING_LIVE)

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "title": self.title,
            "status": self.meetingStatus,
            "organizerId": str(self.organizerId),
            "conversationId": str(self.conversationId),
        }


class MeetingParticipant(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        userId: uuid.UUID,
        status: str,
        createdAt: datetime,
        *,
        role: str = "PARTICIPANT",  # Phase 10 §29 HOST|CO_HOST|PARTICIPANT|GUEST
        attendanceDuration: int = 0,  # Phase 10 §29 cumulative seconds in-meeting
        respondedAt: datetime | None = None,
        joinedAt: datetime | None = None,
        leftAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.meetingId = meetingId
        self.userId = userId
        self.status = status
        self.role = role
        self.attendanceDuration = attendanceDuration
        self.createdAt = createdAt
        self.respondedAt = respondedAt
        self.joinedAt = joinedAt
        self.leftAt = leftAt

    @staticmethod
    def invite(
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        userId: uuid.UUID,
        now: datetime,
        role: str = "PARTICIPANT",
    ) -> MeetingParticipant:
        participant = MeetingParticipant(
            id=newId(),
            tenantId=tenantId,
            meetingId=meetingId,
            userId=userId,
            status=MEETING_INVITED,
            createdAt=now,
            role=role,
        )
        participant.recordEvent(
            DomainEvent(
                name="participantInvitedToMeeting",
                occurredAt=now,
                tenantId=tenantId,
                payload={"meetingId": str(meetingId)},
            )
        )
        return participant

    def rsvp(self, accepted: bool, now: datetime) -> None:
        if self.status not in (MEETING_INVITED, MEETING_ACCEPTED, MEETING_DECLINED):
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Cannot respond after joining.")
        self.status = MEETING_ACCEPTED if accepted else MEETING_DECLINED
        self.respondedAt = now

    def join(self, now: datetime) -> None:
        if self.status == MEETING_JOINED:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Already joined.")
        if self.status == MEETING_LEFT:
            # re-join allowed (connection drop) — §13 joined/left history
            self.joinedAt = now
            self.leftAt = None
            self.status = MEETING_JOINED
            self.recordEvent(
                DomainEvent(
                    name="participantJoinedMeeting",
                    occurredAt=now,
                    tenantId=self.tenantId,
                    actorId=self.userId,
                )
            )
            return
        self.status = MEETING_JOINED
        self.joinedAt = now
        self.recordEvent(
            DomainEvent(
                name="participantJoinedMeeting",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=self.userId,
            )
        )

    def leave(self, now: datetime) -> None:
        if self.status != MEETING_JOINED:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Not currently joined.")
        self.status = MEETING_LEFT
        if self.joinedAt is not None:
            # Phase 10 §29 — accumulate attended seconds across join/leave cycles.
            self.attendanceDuration += max(
                0, int((now - self.joinedAt).total_seconds())
            )
        self.leftAt = now
        self.recordEvent(
            DomainEvent(
                name="participantLeftMeeting",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=self.userId,
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "meetingId": str(self.meetingId),
            "userId": str(self.userId),
            "status": self.status,
            "role": self.role,
            "attendanceDuration": self.attendanceDuration,
        }
