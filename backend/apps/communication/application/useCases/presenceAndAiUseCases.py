"""Presence + AI use cases (Phase 08 §7, §21) and the realtime relay
services used by the WebSocket gateway (typing §31, read receipts §32,
signaling §11 — all ephemeral or delegated, never business rules in the
consumer).
"""

from __future__ import annotations

import uuid

from apps.communication.application.commands.communicationCommands import (
    UpdatePresenceCommand,
)
from apps.communication.application.dto.communicationDtos import AiSummaryDto
from apps.communication.application.queries.communicationQueries import PresenceQuery
from apps.communication.application.services.communicationSupport import (
    CommunicationUseCase,
)
from apps.communication.application.useCases.conversationUseCases import actorOf
from apps.communication.domain.repositories.communicationRepositories import (
    MeetingParticipantRepository,
    MeetingRepository,
    ParticipantRepository,
    PresenceRepository,
)
from apps.communication.domain.valueObjects.communicationTypes import (
    PRESENCE_IN_MEETING,
    PresenceStatus,
)
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid

PRESENCE_TTL_SECONDS = 90  # §7 — presence is ephemeral with TTL heartbeat


class UpdatePresenceUseCase(CommunicationUseCase[UpdatePresenceCommand, object]):
    """§7 — store in the ephemeral presence repository (Redis in prod)."""

    requiredAction = ""

    def __init__(
        self,
        presenceRepository: PresenceRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.presenceRepository = presenceRepository
        self.participantRepository = participantRepository

    def validateCommand(self, command: UpdatePresenceCommand) -> None:
        PresenceStatus(command.status)

    def perform(self, command: UpdatePresenceCommand) -> object:
        actorId, tenantId = actorOf()
        now = self.clock.nowUtc()
        self.presenceRepository.set(
            tenantId, actorId, command.status, PRESENCE_TTL_SECONDS, now
        )
        for conversationId in self.participantRepository.activeConversationIdsOf(actorId):
            self.realtime.toConversation(
                conversationId,
                {
                    "type": "presence.updated",
                    "userId": str(actorId),
                    "status": command.status,
                },
            )
        return {"presence": command.status}


class GetPresenceUseCase(CommunicationUseCase[PresenceQuery, dict]):
    requiredAction = ""

    def __init__(
        self,
        presenceRepository: PresenceRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.presenceRepository = presenceRepository

    def perform(self, query: PresenceQuery) -> dict:
        _, tenantId = actorOf()
        ids = [part.strip() for part in query.userIds.split(",") if part.strip()]
        if not ids:
            return {"presence": {}}
        return {
            "presence": self.presenceRepository.getMany(
                tenantId, [asUuid(value) for value in ids[:100]]
            )
        }


class GenerateMeetingSummaryUseCase(CommunicationUseCase[object, AiSummaryDto]):
    """§21 — AI consumes communication data through a port and writes back
    through application services; it never mutates the domain directly.

    Source material comes from the meeting conversation's SYSTEM/AI-visible
    messages; the AI port stays provider-neutral."""

    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        transcriptReader: object,
        aiAssistant: object,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository
        self.transcriptReader = transcriptReader
        self.aiAssistant = aiAssistant

    def perform(self, command: object) -> AiSummaryDto:
        actorId, tenantId = actorOf()
        meetingId = getattr(command, "meetingId", "")
        meeting = self.meetingRepository.getById(asUuid(meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", str(meetingId))
        participant = self.meetingParticipantRepository.get(meeting.id, actorId)
        if participant is None:
            raise PermissionDeniedError(action="meeting.summary")
        transcript = self.transcriptReader.linesOf(meeting.conversationId)
        if not transcript:
            raise ValidationFailedError(
                "Nothing to summarize.", fieldErrors={"meetingId": "empty transcript"}
            )
        summary = self.aiAssistant.summarize(transcript)
        actionItems = self.aiAssistant.extractActionItems(transcript)
        self.emitIntegrationEvent(
            tenantId,
            "AISummaryGenerated",
            {"meetingId": str(meeting.id), "actionItems": len(actionItems)},
        )
        self.emitIntegrationEvent(
            tenantId,
            "AIActionItemsGenerated",
            {"meetingId": str(meeting.id), "items": actionItems[:20]},
        )
        self.broadcastMeeting(meeting.id, {"type": "meeting.aiSummary"})
        self.audit(
            "CREATE",
            resourceType="MeetingSummary",
            resourceId=str(meeting.id),
            tenantId=tenantId,
            after={"actionItems": len(actionItems)},
        )
        return AiSummaryDto(meetingId=str(meeting.id), summary=summary, actionItems=actionItems)


class RealtimeRelayService:
    """Application service behind the WebSocket gateway (§8 thin consumer).

    typing.start/stop (§31): ephemeral relay — no SQL writes at all.
    """

    def __init__(
        self,
        participantRepository: ParticipantRepository,
        presenceRepository: PresenceRepository,
        realtime: object,
    ) -> None:
        self.participantRepository = participantRepository
        self.presenceRepository = presenceRepository
        self.realtime = realtime

    def activeMembership(self, conversationId: uuid.UUID, userId: uuid.UUID) -> bool:
        participant = self.participantRepository.get(conversationId, userId)
        return participant is not None and participant.isActive()

    def relayTyping(
        self,
        *,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        conversationId: uuid.UUID,
        isTyping: bool,
    ) -> bool:
        """§31 — validate membership, relay ephemeral indicator."""
        if not self.activeMembership(conversationId, userId):
            return False
        del tenantId
        self.realtime.toConversation(
            conversationId,
            {
                "type": "typing.started" if isTyping else "typing.stopped",
                "userId": str(userId),
            },
        )
        return True

    def markOnline(
        self, tenantId: uuid.UUID, userId: uuid.UUID, now: object
    ) -> None:
        self.presenceRepository.set(
            tenantId, userId, "ONLINE", PRESENCE_TTL_SECONDS, now
        )

    def markOffline(
        self, tenantId: uuid.UUID, userId: uuid.UUID, now: object
    ) -> None:
        self.presenceRepository.set(
            tenantId, userId, "OFFLINE", PRESENCE_TTL_SECONDS, now
        )

    def markInMeeting(
        self, tenantId: uuid.UUID, userId: uuid.UUID, now: object
    ) -> None:
        self.presenceRepository.set(
            tenantId, userId, PRESENCE_IN_MEETING, PRESENCE_TTL_SECONDS, now
        )
