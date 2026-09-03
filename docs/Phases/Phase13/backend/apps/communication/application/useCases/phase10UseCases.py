"""Phase 10 application use cases (docs/Phases/Phase10.md).

Covers the capabilities Phase 10 adds on top of the Phase 08 platform:
- message revision history (§11),
- meeting transcripts + segments (§34/§35),
- granular meeting capability overrides + the §30 permission matrix,
- user blocks across direct message / call / meeting invitation (§70),
- provider-agnostic call session bootstrap (§25).

Every use case follows the kernel template (validate -> authorize -> business
rules -> persist in UoW -> events post-commit). Blocks are enforced through a
small domain policy reused by the send/invite flows.
"""

from __future__ import annotations

import uuid

from apps.communication.application.commands.phase10Commands import (
    BlockUserCommand,
    CheckMeetingCapabilityQuery,
    CompleteTranscriptCommand,
    CreateCallSessionCommand,
    GetTranscriptQuery,
    JoinCallSessionCommand,
    ListBlocksQuery,
    ListMessageRevisionsQuery,
    RequestTranscriptCommand,
    SetMeetingCapabilityCommand,
    TranscriptSegmentInput,
    UnblockUserCommand,
)
from apps.communication.application.dto.phase10Dtos import (
    CallSessionDto,
    MeetingCapabilityDto,
    MessageRevisionDto,
    TranscriptDto,
    UserBlockDto,
    blockDtoFromDomain,
    revisionDtoFromDomain,
    transcriptDtoFromDomain,
)
from apps.communication.application.services.communicationSupport import (
    CommunicationUseCase,
)
from apps.communication.domain.entities.phase10Records import (
    MeetingTranscript,
    TranscriptSegment,
    UserBlock,
)
from apps.communication.domain.repositories.communicationRepositories import (
    CallRepository,
    MeetingParticipantRepository,
    MeetingRepository,
    MessageRepository,
    ParticipantRepository,
)
from apps.communication.domain.repositories.phase10Repositories import (
    CallProvider,
    CapabilityOverride,
    MeetingCapabilityRepository,
    MessageRevisionRepository,
    TranscriptRepository,
    UserBlockRepository,
)
from apps.communication.domain.services import meetingPermissions
from apps.communication.domain.valueObjects import phase10Types as types
from apps.sharedKernel.domain.errors import (
    BusinessRuleViolationError,
    EntityNotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid

# ---------------------------------------------------------------------------
# message revisions (§11)
# ---------------------------------------------------------------------------


class ListMessageRevisionsUseCase(
    CommunicationUseCase[ListMessageRevisionsQuery, list[MessageRevisionDto]]
):
    requiredAction = ""

    def __init__(
        self,
        messageRepository: MessageRepository,
        participantRepository: ParticipantRepository,
        revisionRepository: MessageRevisionRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.messageRepository = messageRepository
        self.participantRepository = participantRepository
        self.revisionRepository = revisionRepository

    def perform(self, query: ListMessageRevisionsQuery) -> list[MessageRevisionDto]:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        actorId = asUuid(context.actorId)
        messageId = asUuid(query.messageId)

        message = self.messageRepository.getById(messageId, tenantId)
        if message is None:
            raise EntityNotFoundError("Message", query.messageId)
        participant = self.participantRepository.get(message.conversationId, actorId)
        if participant is None or not participant.isActive():
            raise PermissionDeniedError(action="message.revisions")

        revisions = self.revisionRepository.listForMessage(tenantId, messageId)
        return [revisionDtoFromDomain(r) for r in revisions]


# ---------------------------------------------------------------------------
# transcripts (§34/§35)
# ---------------------------------------------------------------------------


class RequestTranscriptUseCase(CommunicationUseCase[RequestTranscriptCommand, TranscriptDto]):
    requiredAction = "meeting.manage"

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        transcriptRepository: TranscriptRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.transcriptRepository = transcriptRepository

    def perform(self, command: RequestTranscriptCommand) -> TranscriptDto:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        actorId = asUuid(context.actorId)
        meetingId = asUuid(command.meetingId)

        meeting = self.meetingRepository.getById(meetingId, tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)

        existing = self.transcriptRepository.findForMeeting(tenantId, meetingId)
        if existing is not None:
            return transcriptDtoFromDomain(existing)

        transcript = MeetingTranscript.request(
            tenantId=tenantId,
            meetingId=meetingId,
            requestedBy=actorId,
            language=command.language or "en-US",
            now=self.clock.nowUtc(),
        )
        self.transcriptRepository.create(transcript)
        self.collectEventsFrom(transcript)
        self.audit(
            "CREATE",
            "MeetingTranscript",
            str(transcript.id),
            tenantId,
            after={"meetingId": str(meetingId), "language": transcript.language},
        )
        return transcriptDtoFromDomain(transcript)


class CompleteTranscriptUseCase(
    CommunicationUseCase[CompleteTranscriptCommand, TranscriptDto]
):
    """Mark a transcript READY with its content reference and segments.

    The transcription engine (external/AI) supplies segments; this use case
    validates and persists them, then emits ``transcriptReady`` for the
    notification/AI consumers (§36 AI summary flow).
    """

    requiredAction = "meeting.manage"

    def __init__(self, transcriptRepository: TranscriptRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.transcriptRepository = transcriptRepository

    def perform(self, command: CompleteTranscriptCommand) -> TranscriptDto:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        transcriptId = asUuid(command.transcriptId)

        transcript = self.transcriptRepository.getById(transcriptId, tenantId)
        if transcript is None:
            raise EntityNotFoundError("MeetingTranscript", command.transcriptId)
        if not command.contentReference.strip():
            raise ValidationFailedError(
                "contentReference is required to complete a transcript.",
                fieldErrors={"contentReference": "empty"},
            )

        if transcript.transcriptStatus == types.TRANSCRIPT_PENDING:
            transcript.transitionTo(types.TRANSCRIPT_PROCESSING, self.clock.nowUtc())
            self.transcriptRepository.update(transcript)

        segments = self._buildSegments(tenantId, transcript.id, command.segments)
        for segment in segments:
            self.transcriptRepository.addSegment(segment)
        transcript.applySegmentCount(len(segments))
        transcript.transitionTo(
            types.TRANSCRIPT_READY,
            self.clock.nowUtc(),
            contentReference=command.contentReference,
        )
        self.transcriptRepository.update(transcript)
        self.collectEventsFrom(transcript)
        self.emitIntegrationEvent(
            tenantId,
            "TranscriptReady",
            {
                "transcriptId": str(transcript.id),
                "meetingId": str(transcript.meetingId),
                "language": transcript.language,
                "segmentCount": transcript.segmentCount,
            },
        )
        persisted = self.transcriptRepository.listSegments(tenantId, transcript.id)
        return transcriptDtoFromDomain(transcript, persisted)

    @staticmethod
    def _buildSegments(
        tenantId: uuid.UUID,
        transcriptId: uuid.UUID,
        inputs: list[TranscriptSegmentInput],
    ) -> list[TranscriptSegment]:
        from apps.sharedKernel.domain.entities import newId

        segments: list[TranscriptSegment] = []
        for order, item in enumerate(inputs, start=1):
            if not item.text.strip():
                continue
            speaker = asUuid(item.speakerId) if item.speakerId else None
            segments.append(
                TranscriptSegment(
                    id=newId(),
                    tenantId=tenantId,
                    transcriptId=transcriptId,
                    sequence=order,
                    speakerId=speaker,
                    startTimeSeconds=float(item.startTimeSeconds),
                    endTimeSeconds=float(item.endTimeSeconds),
                    text=item.text,
                    confidence=float(item.confidence),
                )
            )
        return segments


class GetTranscriptUseCase(CommunicationUseCase[GetTranscriptQuery, TranscriptDto]):
    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        participantRepository: ParticipantRepository,
        transcriptRepository: TranscriptRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.participantRepository = participantRepository
        self.transcriptRepository = transcriptRepository

    def perform(self, query: GetTranscriptQuery) -> TranscriptDto:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        actorId = asUuid(context.actorId)
        meetingId = asUuid(query.meetingId)

        meeting = self.meetingRepository.getById(meetingId, tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", query.meetingId)
        # participant in the meeting's conversation OR organizer
        participant = self.participantRepository.get(meeting.conversationId, actorId)
        if participant is None and actorId != meeting.organizerId:
            raise PermissionDeniedError(action="meeting.transcript.read")

        transcript = self.transcriptRepository.findForMeeting(tenantId, meetingId)
        if transcript is None:
            raise EntityNotFoundError("MeetingTranscript", query.meetingId)
        if transcript.isReady():
            segments = self.transcriptRepository.listSegments(tenantId, transcript.id)
            return transcriptDtoFromDomain(transcript, segments)
        return transcriptDtoFromDomain(transcript)


# ---------------------------------------------------------------------------
# granular meeting capabilities (§30)
# ---------------------------------------------------------------------------


class SetMeetingCapabilityUseCase(
    CommunicationUseCase[SetMeetingCapabilityCommand, MeetingCapabilityDto]
):
    def __init__(
        self,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        capabilityRepository: MeetingCapabilityRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository
        self.capabilityRepository = capabilityRepository

    requiredAction = "meeting.manage"

    def perform(self, command: SetMeetingCapabilityCommand) -> MeetingCapabilityDto:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        actorId = asUuid(context.actorId)
        meetingId = asUuid(command.meetingId)
        targetUserId = asUuid(command.userId)

        if command.capability not in types.MEETING_CAPABILITIES:
            raise ValidationFailedError(
                "Unknown meeting capability.",
                fieldErrors={"capability": command.capability},
            )

        meeting = self.meetingRepository.getById(meetingId, tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)

        actorPart = self.meetingParticipantRepository.get(meetingId, actorId)
        actorRole = actorPart.role if actorPart is not None else ""
        # only HOST / CO_HOST (or organizer) may override capabilities
        if actorId != meeting.organizerId and not meetingPermissions.isPrivilegedRole(
            actorRole
        ):
            raise PermissionDeniedError(action="meeting.capability.set")

        override = CapabilityOverride(
            meetingId=meetingId,
            userId=targetUserId,
            capability=command.capability,
            granted=bool(command.granted),
            tenantId=tenantId,
        )
        self.capabilityRepository.setOverride(override)
        self.audit(
            "UPDATE",
            "MeetingCapability",
            str(meetingId),
            tenantId,
            after={
                "userId": str(targetUserId),
                "capability": command.capability,
                "granted": bool(command.granted),
            },
        )
        return MeetingCapabilityDto(
            meetingId=str(meetingId),
            userId=str(targetUserId),
            capability=command.capability,
            granted=bool(command.granted),
            source="OVERRIDE",
        )


class CheckMeetingCapabilityUseCase(
    CommunicationUseCase[CheckMeetingCapabilityQuery, MeetingCapabilityDto]
):
    """Resolve an effective capability: role default (§30 matrix) unless a
    per-meeting override exists. Used by join/share/record/end guards."""

    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        capabilityRepository: MeetingCapabilityRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository
        self.capabilityRepository = capabilityRepository

    def perform(self, query: CheckMeetingCapabilityQuery) -> MeetingCapabilityDto:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        actorId = asUuid(context.actorId) if not query.userId else asUuid(query.userId)
        meetingId = asUuid(query.meetingId)

        meeting = self.meetingRepository.getById(meetingId, tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", query.meetingId)

        participant = self.meetingParticipantRepository.get(meetingId, actorId)
        role = participant.role if participant is not None else ""
        invited = participant is not None

        override = self.capabilityRepository.find(
            tenantId, meetingId, actorId, query.capability
        )
        if override is not None:
            granted = override.granted and meetingPermissions.can(
                query.capability,
                userId=actorId,
                organizerId=meeting.organizerId,
                participantRole=role,
                isInvited=invited,
                meetingIsLive=meeting.isLive(),
            ) if override.granted else False
            return MeetingCapabilityDto(
                meetingId=str(meetingId),
                userId=str(actorId),
                capability=query.capability,
                granted=granted,
                source="OVERRIDE",
            )

        granted = meetingPermissions.can(
            query.capability,
            userId=actorId,
            organizerId=meeting.organizerId,
            participantRole=role,
            isInvited=invited,
            meetingIsLive=meeting.isLive(),
        )
        return MeetingCapabilityDto(
            meetingId=str(meetingId),
            userId=str(actorId),
            capability=query.capability,
            granted=granted,
            source="ROLE",
        )


# ---------------------------------------------------------------------------
# user blocks (§70)
# ---------------------------------------------------------------------------


class BlockUserUseCase(CommunicationUseCase[BlockUserCommand, UserBlockDto]):
    def __init__(self, blockRepository: UserBlockRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.blockRepository = blockRepository

    requiredAction = ""

    def perform(self, command: BlockUserCommand) -> UserBlockDto:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        blockerId = asUuid(context.actorId)
        blockedId = asUuid(command.blockedUserId)

        scopes = tuple(command.scopes) if command.scopes else tuple(types.BLOCK_SCOPES)
        block = UserBlock.create(
            tenantId=tenantId,
            blockerId=blockerId,
            blockedUserId=blockedId,
            scopes=scopes,
            now=self.clock.nowUtc(),
            reason=command.reason,
        )
        existing = self.blockRepository.findActive(tenantId, blockerId, blockedId)
        if existing is not None:
            # idempotent re-block: return the existing active block
            return blockDtoFromDomain(existing)
        self.blockRepository.add(block)
        self.collectEventsFrom(block)
        self.audit(
            "CREATE",
            "UserBlock",
            str(block.id),
            tenantId,
            after={"blockedUserId": str(blockedId), "scopes": list(block.scopes)},
        )
        return blockDtoFromDomain(block)


class UnblockUserUseCase(CommunicationUseCase[UnblockUserCommand, UserBlockDto]):
    requiredAction = ""

    def __init__(self, blockRepository: UserBlockRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.blockRepository = blockRepository

    def perform(self, command: UnblockUserCommand) -> UserBlockDto:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        blockerId = asUuid(context.actorId)
        blockedId = asUuid(command.blockedUserId)

        block = self.blockRepository.findActive(tenantId, blockerId, blockedId)
        if block is None:
            raise EntityNotFoundError("UserBlock", command.blockedUserId)
        block.lift(self.clock.nowUtc())
        self.blockRepository.update(block)
        self.collectEventsFrom(block)
        return blockDtoFromDomain(block)


class ListBlocksUseCase(CommunicationUseCase[ListBlocksQuery, list[UserBlockDto]]):
    requiredAction = ""

    def __init__(self, blockRepository: UserBlockRepository, **kernel: object) -> None:
        super().__init__(**kernel)
        self.blockRepository = blockRepository

    def perform(self, query: ListBlocksQuery) -> list[UserBlockDto]:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        blockerId = asUuid(context.actorId)
        blocks = self.blockRepository.listForBlocker(tenantId, blockerId)
        return [blockDtoFromDomain(b) for b in blocks]


def assertNotBlocked(
    blockRepository: UserBlockRepository,
    tenantId: uuid.UUID,
    senderId: uuid.UUID,
    recipientId: uuid.UUID,
    scope: str,
) -> None:
    """§70 policy guard reused by send-message / call / invite flows.

    A block is directional: if EITHER side has blocked the other for this
    scope, the interaction is refused. Organizational policy may later exempt
    privileged contexts; by default the block stands.
    """
    for blocker, blocked in ((recipientId, senderId), (senderId, recipientId)):
        block = blockRepository.findActive(tenantId, blocker, blocked)
        if block is not None and block.covers(scope):
            raise BusinessRuleViolationError(
                f"This interaction is blocked for scope {scope}.",
                ruleId="PHASE10-BR_UserBlock",
            )


# ---------------------------------------------------------------------------
# provider-agnostic call session (§25)
# ---------------------------------------------------------------------------


class CreateCallSessionUseCase(
    CommunicationUseCase[CreateCallSessionCommand, CallSessionDto]
):
    requiredAction = ""

    def __init__(
        self,
        callRepository: CallRepository,
        callProvider: CallProvider,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.callRepository = callRepository
        self.callProvider = callProvider

    def perform(self, command: CreateCallSessionCommand) -> CallSessionDto:
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        tenantId = asUuid(context.actorTenantId)
        callId = asUuid(command.callId)

        call = self.callRepository.getById(callId, tenantId)
        if call is None:
            raise EntityNotFoundError("Call", command.callId)

        info = self.callProvider.createSession(
            callId=callId,
            mediaType=command.mediaType or "AUDIO",
            tenantId=tenantId,
        )
        return CallSessionDto(
            provider=info["provider"],
            sessionRef=info["sessionRef"],
            mediaType=info["mediaType"],
            transport=info.get("transport", "webrtc-signaling"),
        )


class JoinCallSessionUseCase(CommunicationUseCase[JoinCallSessionCommand, dict]):
    requiredAction = ""

    def __init__(self, callProvider: CallProvider, **kernel: object) -> None:
        super().__init__(**kernel)
        self.callProvider = callProvider

    def perform(self, command: JoinCallSessionCommand) -> dict:
        sessionRef = f"wrtc-{command.callId}"
        from apps.sharedKernel.application.requestContext import currentContext

        actorId = asUuid(currentContext().actorId)
        return self.callProvider.joinSession(sessionRef=sessionRef, userId=actorId)
