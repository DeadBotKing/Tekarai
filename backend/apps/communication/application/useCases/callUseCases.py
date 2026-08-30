"""Call use cases (Phase 08 §10–§12, §14, §24).

The backend is NOT the media transport (§10): WebRTC peers exchange media
directly (or via an SFU in group mode §12). Tekarai owns call sessions,
authorization, participant state, the versioned signaling relay (§11) and
audit. Call initiation is idempotent (§24).
"""

from __future__ import annotations

import uuid

from apps.communication.application.commands.communicationCommands import (
    AcceptCallCommand,
    EndCallCommand,
    RejectCallCommand,
    RelaySignalCommand,
    StartCallCommand,
)
from apps.communication.application.dto.communicationDtos import CallDto
from apps.communication.application.queries.communicationQueries import GetCallQuery
from apps.communication.application.services.communicationSupport import (
    CommunicationUseCase,
)
from apps.communication.application.useCases.conversationUseCases import actorOf
from apps.communication.domain.entities.call import Call, CallParticipant
from apps.communication.domain.repositories.communicationRepositories import (
    CallParticipantRepository,
    CallRepository,
    ConversationRepository,
    MediaRouter,
    MeetingRepository,
    ParticipantRepository,
)
from apps.communication.domain.services.communicationRules import SignalingProtocol
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    PermissionDeniedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


class StartCallUseCase(CommunicationUseCase[StartCallCommand, CallDto]):
    """§10 — create the call session; signaling goes over the socket."""

    requiredAction = ""

    def __init__(
        self,
        callRepository: CallRepository,
        callParticipantRepository: CallParticipantRepository,
        conversationRepository: ConversationRepository,
        meetingRepository: MeetingRepository,
        participantRepository: ParticipantRepository,
        mediaRouter: MediaRouter,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.callRepository = callRepository
        self.callParticipantRepository = callParticipantRepository
        self.conversationRepository = conversationRepository
        self.meetingRepository = meetingRepository
        self.participantRepository = participantRepository
        self.mediaRouter = mediaRouter

    def perform(self, command: StartCallCommand) -> CallDto:
        actorId, tenantId = actorOf()
        # §24 — call initiation idempotency
        if command.clientRequestId:
            existing = self.callRepository.findByIdempotencyKey(
                tenantId, actorId, command.clientRequestId
            )
            if existing is not None:
                return callDto(existing)

        conversationId = asUuid(command.conversationId) if command.conversationId else None
        meetingId = asUuid(command.meetingId) if command.meetingId else None
        if conversationId is not None:
            conversation = self.conversationRepository.getById(conversationId, tenantId)
            if conversation is None or not conversation.isActive:
                raise EntityNotFoundError("Conversation", command.conversationId)
            member = self.participantRepository.get(conversation.id, actorId)
            if member is None or not member.isActive():
                raise PermissionDeniedError(action="call.start")
            for peer in self.participantRepository.activeUserIdsOf(conversation.id):
                if peer != actorId:
                    self.broadcastUser(
                        peer,
                        {"type": "call.incoming", "conversationId": str(conversation.id)},
                    )
        elif meetingId is not None:
            meeting = self.meetingRepository.getById(meetingId, tenantId)
            if meeting is None:
                raise EntityNotFoundError("Meeting", command.meetingId)
            if not meeting.isLive():
                from apps.sharedKernel.domain.errors import ConflictError

                raise ConflictError("Group calls require a LIVE meeting (§12).")

        now = self.clock.nowUtc()
        self._metrics().increment("callsStarted")
        self._metrics().increment("activeCalls")  # §39 gauge
        call = Call.start(
            tenantId,
            actorId,
            command.mediaType,
            now,
            conversationId=conversationId,
            meetingId=meetingId,
            clientRequestId=command.clientRequestId,
        )
        call.mediaSessionRef = self.mediaRouter.openSession(
            str(call.id), command.mediaType
        )  # §12 — SFU adapter may be a no-op for peer-to-peer
        self.callRepository.create(call)
        self.callParticipantRepository.add(
            CallParticipant.join(tenantId, call.id, actorId, now)
        )
        self.collectEventsFrom(call)
        self.emitIntegrationEvent(
            tenantId, "CallStarted", {"callId": str(call.id), "mediaType": call.mediaType}
        )
        self.audit(
            "CREATE",
            resourceType="Call",
            resourceId=str(call.id),
            tenantId=tenantId,
            after={"mediaType": command.mediaType},
        )
        return callDto(call)


class AcceptCallUseCase(CommunicationUseCase[AcceptCallCommand, CallDto]):
    """RINGING → ACTIVE; the acceptor must belong to the call's conversation."""

    requiredAction = ""

    def __init__(
        self,
        callRepository: CallRepository,
        callParticipantRepository: CallParticipantRepository,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        mediaRouter: MediaRouter,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.callRepository = callRepository
        self.callParticipantRepository = callParticipantRepository
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.mediaRouter = mediaRouter

    def perform(self, command: AcceptCallCommand) -> CallDto:
        actorId, tenantId = actorOf()
        call = self.loadCall(command.callId, tenantId)
        if call.conversationId is not None:
            member = self.participantRepository.get(call.conversationId, actorId)
            if member is None or not member.isActive():
                raise PermissionDeniedError(action="call.accept")
        call.accept(self.clock.nowUtc())
        self.callRepository.update(call)
        now = self.clock.nowUtc()
        leg = self.callParticipantRepository.get(call.id, actorId)
        if leg is None:
            self.callParticipantRepository.add(
                CallParticipant.join(tenantId, call.id, actorId, now)
            )
        self.collectEventsFrom(call)
        if call.mediaSessionRef:
            self.mediaRouter.joinSession(call.mediaSessionRef, str(actorId))
        self.emitIntegrationEvent(tenantId, "CallAccepted", {"callId": str(call.id)})
        self.broadcastCall(call.id, {"type": "call.accepted"})
        self.audit(
            "UPDATE",
            resourceType="Call",
            resourceId=str(call.id),
            tenantId=tenantId,
            after={"status": call.callStatus},
        )
        return callDto(call)

    def loadCall(self, callId: str, tenantId: uuid.UUID) -> Call:
        call = self.callRepository.getById(asUuid(callId), tenantId)
        if call is None:
            raise EntityNotFoundError("Call", callId)
        return call


class RejectCallUseCase(CommunicationUseCase[RejectCallCommand, CallDto]):
    requiredAction = ""

    def __init__(
        self,
        callRepository: CallRepository,
        callParticipantRepository: CallParticipantRepository,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.callRepository = callRepository
        self.callParticipantRepository = callParticipantRepository
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, command: RejectCallCommand) -> CallDto:
        actorId, tenantId = actorOf()
        call = self.callRepository.getById(asUuid(command.callId), tenantId)
        if call is None:
            raise EntityNotFoundError("Call", command.callId)
        if call.conversationId is not None:
            member = self.participantRepository.get(call.conversationId, actorId)
            if member is None or not member.isActive():
                raise PermissionDeniedError(action="call.reject")
        call.reject(self.clock.nowUtc())
        self.callRepository.update(call)
        self._metrics().decrement("activeCalls")  # §39 gauge — leg closed
        self.collectEventsFrom(call)
        self.emitIntegrationEvent(tenantId, "CallRejected", {"callId": str(call.id)})
        self.broadcastCall(call.id, {"type": "call.rejected"})
        return callDto(call)


class EndCallUseCase(CommunicationUseCase[EndCallCommand, CallDto]):
    """Any active leg may hang up; all legs are closed and audited."""

    requiredAction = ""

    def __init__(
        self,
        callRepository: CallRepository,
        callParticipantRepository: CallParticipantRepository,
        mediaRouter: MediaRouter,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.callRepository = callRepository
        self.callParticipantRepository = callParticipantRepository
        self.mediaRouter = mediaRouter

    def perform(self, command: EndCallCommand) -> CallDto:
        actorId, tenantId = actorOf()
        call = self.callRepository.getById(asUuid(command.callId), tenantId)
        if call is None:
            raise EntityNotFoundError("Call", command.callId)
        leg = self.callParticipantRepository.get(call.id, actorId)
        if leg is None:
            raise PermissionDeniedError(action="call.end")
        now = self.clock.nowUtc()
        for participant in self.callParticipantRepository.listForCall(call.id):
            if participant.isActive():
                participant.leave(now)
                self.callParticipantRepository.update(participant)
        call.end(now)
        self.callRepository.update(call)
        self._metrics().decrement("activeCalls")  # §39 gauge
        if call.mediaSessionRef:
            self.mediaRouter.leaveSession(call.mediaSessionRef, str(actorId))
        self.collectEventsFrom(call)
        self.emitIntegrationEvent(tenantId, "CallEnded", {"callId": str(call.id)})
        self.broadcastCall(call.id, {"type": "call.ended"})
        self.audit(
            "UPDATE",
            resourceType="Call",
            resourceId=str(call.id),
            tenantId=tenantId,
            after={"finalState": call.callStatus},
        )
        return callDto(call)


class RelaySignalUseCase(CommunicationUseCase[RelaySignalCommand, object]):
    """§11 — validate + relay a ``communication.signal.v1`` envelope.

    The backend never interprets SDP/ICE payloads; it checks membership and
    state, stamps the sender identity (§17) and forwards the envelope.
    """

    requiredAction = ""

    def __init__(
        self,
        callRepository: CallRepository,
        callParticipantRepository: CallParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.callRepository = callRepository
        self.callParticipantRepository = callParticipantRepository

    def perform(self, command: RelaySignalCommand) -> object:
        actorId, tenantId = actorOf()
        kind, callIdText, payload = SignalingProtocol.validate(command.envelope)
        call = self.callRepository.getById(asUuid(callIdText), tenantId)
        if call is None:
            self.noteSignalingFailure()  # §39
            raise EntityNotFoundError("Call", callIdText)
        leg = self.callParticipantRepository.get(call.id, actorId)
        if leg is None or not leg.isActive():
            self.noteSignalingFailure()  # §39 failedSignalingRequests
            raise PermissionDeniedError(action="call.signal")

        if kind == "MEDIA_STATE_CHANGE":  # §14 — e.g. screen share toggled
            state = str(payload.get("state", ""))
            leg.setMediaState(state)
            self.callParticipantRepository.update(leg)
            self.audit(
                "UPDATE",
                resourceType="CallParticipant",
                resourceId=str(leg.id),
                tenantId=tenantId,
                after={"mediaState": state},
            )

        envelope = SignalingProtocol.envelope(
            kind, callId=str(call.id), fromUser=str(actorId), payload=payload
        )
        event = {"type": "signal", "envelope": envelope}
        if command.targetUserId:
            self.broadcastUser(asUuid(command.targetUserId), event)
        else:
            self.broadcastCall(call.id, event)
        return {"relayed": True, "kind": kind}


class GetCallUseCase(CommunicationUseCase[GetCallQuery, CallDto]):
    requiredAction = ""

    def __init__(
        self,
        callRepository: CallRepository,
        callParticipantRepository: CallParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.callRepository = callRepository
        self.callParticipantRepository = callParticipantRepository

    def perform(self, query: GetCallQuery) -> CallDto:
        actorId, tenantId = actorOf()
        call = self.callRepository.getById(asUuid(query.callId), tenantId)
        if call is None:
            raise EntityNotFoundError("Call", query.callId)
        leg = self.callParticipantRepository.get(call.id, actorId)
        if leg is None:
            raise PermissionDeniedError(action="call.view")
        return callDto(call)


def callDto(call: Call) -> CallDto:
    return CallDto(
        id=str(call.id),
        mediaType=call.mediaType,
        callStatus=call.callStatus,
        initiatorId=str(call.initiatorId),
        conversationId=str(call.conversationId) if call.conversationId else "",
        meetingId=str(call.meetingId) if call.meetingId else "",
        createdAt=call.createdAt.isoformat(),
        startedAt=call.startedAt.isoformat() if call.startedAt else "",
        endedAt=call.endedAt.isoformat() if call.endedAt else "",
    )
