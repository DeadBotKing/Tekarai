"""Meeting + recording use cases (Phase 08 §13, §15)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from apps.communication.application.commands.communicationCommands import (
    ApproveLetterCommand,
    CancelMeetingCommand,
    CreateLetterCommand,
    CreateMeetingCommand,
    DispatchLetterCommand,
    EndMeetingCommand,
    JoinMeetingCommand,
    LeaveMeetingCommand,
    PublishRecordingCommand,
    ReceiveLetterCommand,
    RsvpMeetingCommand,
    SignLetterCommand,
    StartMeetingCommand,
    StartRecordingCommand,
    StopRecordingCommand,
    SubmitLetterCommand,
)
from apps.communication.application.dto.communicationDtos import (
    LetterDto,
    MeetingDto,
    RecordingDto,
)
from apps.communication.application.queries.communicationQueries import (
    GetMeetingQuery,
    ListLettersQuery,
    ListMeetingsQuery,
    ListRecordingsQuery,
)
from apps.communication.application.services.communicationSupport import (
    CommunicationUseCase,
    UserDirectory,
)
from apps.communication.application.useCases.conversationUseCases import actorOf
from apps.communication.domain.entities.meeting import Meeting, MeetingParticipant
from apps.communication.domain.entities.officialLetter import OfficialLetter
from apps.communication.domain.entities.recording import Recording
from apps.communication.domain.repositories.communicationRepositories import (
    ConversationRepository,
    LetterRepository,
    MeetingParticipantRepository,
    MeetingRepository,
    ParticipantRepository,
    RecordingRepository,
)
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


def parseWhen(value: str) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class CreateMeetingUseCase(CommunicationUseCase[CreateMeetingCommand, MeetingDto]):
    """§13 — schedule a meeting inside a conversation (organizer = actor)."""

    requiredAction = "meeting.manage"

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        userDirectory: UserDirectory,
        blockRepository: object = None,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository
        self.userDirectory = userDirectory
        # Phase 10 §70 — optional so Phase 08 wiring keeps working unchanged.
        self.blockRepository = blockRepository

    def perform(self, command: CreateMeetingCommand) -> MeetingDto:
        actorId, tenantId = actorOf()
        # §24 — meeting creation idempotency
        if command.clientRequestId:
            existing = self.meetingRepository.findByIdempotencyKey(
                tenantId, actorId, command.clientRequestId
            )
            if existing is not None:
                return meetingDto(existing, [])
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None or not conversation.isActive:
            raise EntityNotFoundError("Conversation", command.conversationId)
        organizer = self.participantRepository.get(conversation.id, actorId)
        if organizer is None or not organizer.isActive():
            raise PermissionDeniedError(action="meeting.create")

        now = self.clock.nowUtc()
        meeting = Meeting.schedule(
            tenantId,
            conversation.id,
            actorId,
            command.title,
            now,
            description=command.description,
            scheduledStart=parseWhen(command.scheduledStart),
            scheduledEnd=parseWhen(command.scheduledEnd),
        )
        meeting.clientRequestId = command.clientRequestId
        self.meetingRepository.create(meeting)
        self.meetingParticipantRepository.add(
            MeetingParticipant.invite(
                tenantId, meeting.id, actorId, now, role="HOST"
            )
        )
        for invitee in command.inviteeIds:
            inviteeId = asUuid(invitee)
            if not self.userDirectory.exists(tenantId, inviteeId):
                raise EntityNotFoundError("User", invitee)
            # Phase 10 §70 — a block in either direction blocks an invitation.
            if self.blockRepository is not None:
                from apps.communication.application.useCases.phase10UseCases import (
                    assertNotBlocked,
                )
                from apps.communication.domain.valueObjects import phase10Types as p10

                assertNotBlocked(
                    self.blockRepository,
                    tenantId,
                    actorId,
                    inviteeId,
                    p10.BLOCK_MEETING_INVITATION,
                )
            self.meetingParticipantRepository.add(
                MeetingParticipant.invite(
                    tenantId, meeting.id, inviteeId, now, role="PARTICIPANT"
                )
            )
        self.collectEventsFrom(meeting)
        self.emitIntegrationEvent(
            tenantId,
            "MeetingCreated",
            {"meetingId": str(meeting.id), "title": meeting.title},
        )
        self.audit(
            "CREATE",
            resourceType="Meeting",
            resourceId=str(meeting.id),
            tenantId=tenantId,
            after={"title": meeting.title},
        )
        return meetingDto(meeting, [])


class StartMeetingUseCase(CommunicationUseCase[StartMeetingCommand, MeetingDto]):
    """SCHEDULED/WAITING → LIVE; organizer or meeting moderator only."""

    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository

    def perform(self, command: StartMeetingCommand) -> MeetingDto:
        actorId, tenantId = actorOf()
        meeting = self.loadMeeting(command.meetingId, tenantId)
        if meeting.organizerId != actorId:
            raise PermissionDeniedError(action="meeting.start")
        meeting.start(self.clock.nowUtc())
        self.meetingRepository.update(meeting)
        self._metrics().increment("meetingsStarted")
        self._metrics().increment("activeMeetings")  # §39 gauge
        self.collectEventsFrom(meeting)
        self.emitIntegrationEvent(tenantId, "MeetingStarted", {"meetingId": str(meeting.id)})
        self.broadcastMeeting(meeting.id, {"type": "meeting.started"})
        self.audit(
            "UPDATE",
            resourceType="Meeting",
            resourceId=str(meeting.id),
            tenantId=tenantId,
            after={"status": meeting.meetingStatus},
        )
        return meetingDto(meeting)

    def loadMeeting(self, meetingId: str, tenantId: uuid.UUID) -> Meeting:
        meeting = self.meetingRepository.getById(asUuid(meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", meetingId)
        return meeting


class JoinMeetingUseCase(CommunicationUseCase[JoinMeetingCommand, MeetingDto]):
    """§13 — join a live/waiting meeting the user was invited to (or a
    member of the hosting conversation)."""

    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, command: JoinMeetingCommand) -> MeetingDto:
        actorId, tenantId = actorOf()
        meeting = self.meetingRepository.getById(asUuid(command.meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        if not meeting.isJoinable():
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError(
                f"Meeting is {meeting.meetingStatus} and cannot be joined."
            )
        conversationMember = self.participantRepository.get(
            meeting.conversationId, actorId
        )
        if conversationMember is None or not conversationMember.isActive():
            raise PermissionDeniedError(action="meeting.join")
        now = self.clock.nowUtc()
        participant = self.meetingParticipantRepository.get(meeting.id, actorId)
        if participant is None:
            participant = MeetingParticipant.invite(tenantId, meeting.id, actorId, now)
            self.meetingParticipantRepository.add(participant)
        participant.join(now)
        self.meetingParticipantRepository.update(participant)
        self.collectEventsFrom(participant)
        self.emitIntegrationEvent(
            tenantId,
            "ParticipantJoinedMeeting",
            {"meetingId": str(meeting.id), "userId": str(actorId)},
        )
        self.broadcastMeeting(
            meeting.id,
            {"type": "meeting.participantJoined", "userId": str(actorId)},
        )
        self.audit(
            "UPDATE",
            resourceType="Meeting",
            resourceId=str(meeting.id),
            tenantId=tenantId,
            after={"joinedUserId": str(actorId)},
        )
        return meetingDto(meeting)


class LeaveMeetingUseCase(CommunicationUseCase[LeaveMeetingCommand, object]):
    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository

    def perform(self, command: LeaveMeetingCommand) -> object:
        actorId, tenantId = actorOf()
        meeting = self.meetingRepository.getById(asUuid(command.meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        participant = self.meetingParticipantRepository.get(meeting.id, actorId)
        if participant is None:
            raise PermissionDeniedError(action="meeting.leave")
        participant.leave(self.clock.nowUtc())
        self.meetingParticipantRepository.update(participant)
        self.collectEventsFrom(participant)
        self.emitIntegrationEvent(
            tenantId,
            "ParticipantLeftMeeting",
            {"meetingId": str(meeting.id), "userId": str(actorId)},
        )
        self.broadcastMeeting(
            meeting.id, {"type": "meeting.participantLeft", "userId": str(actorId)}
        )
        return {"left": True}


class RsvpMeetingUseCase(CommunicationUseCase[RsvpMeetingCommand, object]):
    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository

    def perform(self, command: RsvpMeetingCommand) -> object:
        actorId, tenantId = actorOf()
        meeting = self.meetingRepository.getById(asUuid(command.meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        participant = self.meetingParticipantRepository.get(meeting.id, actorId)
        if participant is None:
            raise PermissionDeniedError(action="meeting.rsvp")
        participant.rsvp(command.accepted, self.clock.nowUtc())
        self.meetingParticipantRepository.update(participant)
        self.broadcastMeeting(
            meeting.id,
            {
                "type": "meeting.rsvp",
                "userId": str(actorId),
                "accepted": command.accepted,
            },
        )
        return {"rsvp": "accepted" if command.accepted else "declined"}


class EndMeetingUseCase(CommunicationUseCase[EndMeetingCommand, MeetingDto]):
    """LIVE → ENDED (organizer) — also stops any active recording (§15)."""

    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        recordingRepository: RecordingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.recordingRepository = recordingRepository
        self.meetingParticipantRepository = meetingParticipantRepository

    def perform(self, command: EndMeetingCommand) -> MeetingDto:
        actorId, tenantId = actorOf()
        meeting = self.meetingRepository.getById(asUuid(command.meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        if meeting.organizerId != actorId:
            raise PermissionDeniedError(action="meeting.end")
        now = self.clock.nowUtc()
        activeRecording = self.recordingRepository.findActiveForMeeting(
            tenantId, meeting.id
        )
        if activeRecording is not None:
            activeRecording.transitionTo("STOPPED", now)
            self.recordingRepository.update(activeRecording)
        meeting.transitionTo("ENDED", now)
        self.meetingRepository.update(meeting)
        self._metrics().decrement("activeMeetings")  # §39 gauge
        self.collectEventsFrom(meeting)
        self.emitIntegrationEvent(tenantId, "MeetingEnded", {"meetingId": str(meeting.id)})
        self.broadcastMeeting(meeting.id, {"type": "meeting.ended"})
        self.audit(
            "UPDATE",
            resourceType="Meeting",
            resourceId=str(meeting.id),
            tenantId=tenantId,
            after={"status": "ENDED"},
        )
        return meetingDto(meeting)


class CancelMeetingUseCase(CommunicationUseCase[CancelMeetingCommand, object]):
    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository

    def perform(self, command: CancelMeetingCommand) -> object:
        actorId, tenantId = actorOf()
        meeting = self.meetingRepository.getById(asUuid(command.meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        if meeting.organizerId != actorId:
            raise PermissionDeniedError(action="meeting.cancel")
        meeting.transitionTo("CANCELLED", self.clock.nowUtc())
        self.meetingRepository.update(meeting)
        self.collectEventsFrom(meeting)
        self.emitIntegrationEvent(
            tenantId, "MeetingCancelled", {"meetingId": str(meeting.id)}
        )
        return {"cancelled": True}


class ListMeetingsUseCase(
    CommunicationUseCase[ListMeetingsQuery, list[MeetingDto]]
):
    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository

    def perform(self, query: ListMeetingsQuery) -> list[MeetingDto]:
        actorId, tenantId = actorOf()
        conversations: list[uuid.UUID] = []
        if query.conversationId:
            conversations = [asUuid(query.conversationId)]
        else:
            conversations = self.participantRepository.activeConversationIdsOf(actorId)
        meetings: list[MeetingDto] = []
        for conversationId in conversations:
            for meeting in self.meetingRepository.listByConversation(
                tenantId, conversationId
            ):
                meetings.append(
                    meetingDto(
                        meeting,
                        [
                            {"userId": str(p.userId), "status": p.status}
                            for p in self.meetingParticipantRepository.listForMeeting(
                                meeting.id
                            )
                        ],
                    )
                )
        return meetings


class GetMeetingUseCase(CommunicationUseCase[GetMeetingQuery, MeetingDto]):
    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        meetingParticipantRepository: MeetingParticipantRepository,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.meetingParticipantRepository = meetingParticipantRepository
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, query: GetMeetingQuery) -> MeetingDto:
        actorId, tenantId = actorOf()
        meeting = self.meetingRepository.getById(asUuid(query.meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", query.meetingId)
        member = self.participantRepository.get(meeting.conversationId, actorId)
        if member is None or not member.isActive():
            raise PermissionDeniedError(action="meeting.view")
        return meetingDto(
            meeting,
            [
                {"userId": str(p.userId), "status": p.status}
                for p in self.meetingParticipantRepository.listForMeeting(meeting.id)
            ],
        )


# -- recordings (§15) -------------------------------------------------------------


class StartRecordingUseCase(CommunicationUseCase[StartRecordingCommand, RecordingDto]):
    """Recording is an explicit, permission-guarded capability (§15)."""

    requiredAction = "recording.manage"

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        recordingRepository: RecordingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.recordingRepository = recordingRepository

    def perform(self, command: StartRecordingCommand) -> RecordingDto:
        actorId, tenantId = actorOf()
        meeting = self.meetingRepository.getById(asUuid(command.meetingId), tenantId)
        if meeting is None:
            raise EntityNotFoundError("Meeting", command.meetingId)
        if not meeting.isLive():
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Recording requires a LIVE meeting.")
        active = self.recordingRepository.findActiveForMeeting(tenantId, meeting.id)
        if active is not None:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("A recording is already active for this meeting.")
        now = self.clock.nowUtc()
        recording = Recording.request(tenantId, meeting.id, actorId, now)
        recording.transitionTo("STARTED", now)
        self.recordingRepository.create(recording)
        self.collectEventsFrom(recording)
        self.emitIntegrationEvent(
            tenantId,
            "RecordingStarted",
            {"meetingId": str(meeting.id), "recordingId": str(recording.id)},
        )
        self.broadcastMeeting(meeting.id, {"type": "recording.started"})
        self.audit(
            "CREATE",
            resourceType="Recording",
            resourceId=str(recording.id),
            tenantId=tenantId,
        )
        return recordingDto(recording)


class StopRecordingUseCase(CommunicationUseCase[StopRecordingCommand, RecordingDto]):
    requiredAction = "recording.manage"

    def __init__(
        self,
        recordingRepository: RecordingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.recordingRepository = recordingRepository

    def perform(self, command: StopRecordingCommand) -> RecordingDto:
        actorId, tenantId = actorOf()
        recording = self.recordingRepository.getById(
            asUuid(command.recordingId), tenantId
        )
        if recording is None:
            raise EntityNotFoundError("Recording", command.recordingId)
        recording.transitionTo("STOPPED", self.clock.nowUtc())
        self.recordingRepository.update(recording)
        self.collectEventsFrom(recording)
        self.emitIntegrationEvent(
            tenantId, "RecordingStopped", {"recordingId": str(recording.id)}
        )
        self.broadcastMeeting(recording.meetingId, {"type": "recording.stopped"})
        self.audit(
            "UPDATE",
            resourceType="Recording",
            resourceId=str(recording.id),
            tenantId=tenantId,
        )
        return recordingDto(recording)


class PublishRecordingUseCase(
    CommunicationUseCase[PublishRecordingCommand, RecordingDto]
):
    """PROCESSING → AVAILABLE/FAILED — called by the media pipeline with the
    Documents-subsystem storage reference (§15)."""

    requiredAction = "recording.manage"

    def __init__(
        self,
        recordingRepository: RecordingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.recordingRepository = recordingRepository

    def perform(self, command: PublishRecordingCommand) -> RecordingDto:
        _, tenantId = actorOf()
        recording = self.recordingRepository.getById(
            asUuid(command.recordingId), tenantId
        )
        if recording is None:
            raise EntityNotFoundError("Recording", command.recordingId)
        if recording.recordingStatus not in ("STOPPED", "PROCESSING"):
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Only stopped/processing recordings can be published.")
        now = self.clock.nowUtc()
        if command.failed:
            recording.transitionTo("FAILED", now, reason=command.reason)
        else:
            recording.transitionTo("PROCESSING", now)
            recording.attachStorageRef(command.storageRef)
            recording.transitionTo("AVAILABLE", now)
        self.recordingRepository.update(recording)
        self.collectEventsFrom(recording)
        return recordingDto(recording)


class ListRecordingsUseCase(
    CommunicationUseCase[ListRecordingsQuery, list[RecordingDto]]
):
    requiredAction = ""

    def __init__(
        self,
        meetingRepository: MeetingRepository,
        recordingRepository: RecordingRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.meetingRepository = meetingRepository
        self.recordingRepository = recordingRepository

    def perform(self, query: ListRecordingsQuery) -> list[RecordingDto]:
        _, tenantId = actorOf()
        return [
            recordingDto(r)
            for r in self.recordingRepository.listForMeeting(
                tenantId, asUuid(query.meetingId)
            )
        ]


# -- official letters (§16) ----------------------------------------------------------


class CreateLetterUseCase(CommunicationUseCase[CreateLetterCommand, LetterDto]):
    """§16 — dedicated formal document; reference number minted per tenant."""

    requiredAction = "letter.create"

    def __init__(
        self,
        letterRepository: LetterRepository,
        userDirectory: UserDirectory,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.letterRepository = letterRepository
        self.userDirectory = userDirectory

    def perform(self, command: CreateLetterCommand) -> LetterDto:
        senderId, tenantId = actorOf()
        recipientId = asUuid(command.recipientId)
        if not self.userDirectory.exists(tenantId, recipientId):
            raise EntityNotFoundError("User", command.recipientId)
        if not command.subject.strip():
            raise ValidationFailedError(
                "Letter subject is required.", fieldErrors={"subject": "empty"}
            )
        letter = OfficialLetter.draft(
            tenantId,
            senderId,
            recipientId,
            command.subject,
            self.letterRepository.nextReferenceNumber(tenantId),
            self.clock.nowUtc(),
            body=command.body,
            recipientOrganization=command.recipientOrganization,
            recipientUnit=command.recipientUnit,
        )
        self.letterRepository.create(letter)
        self.collectEventsFrom(letter)
        self.emitIntegrationEvent(
            tenantId,
            "LetterCreated",
            {"referenceNumber": letter.referenceNumber},
        )
        self.audit(
            "CREATE",
            resourceType="OfficialLetter",
            resourceId=str(letter.id),
            tenantId=tenantId,
            after={"referenceNumber": letter.referenceNumber},
        )
        return letterDto(letter)


class LetterTransitionUseCase(
    CommunicationUseCase[SubmitLetterCommand, LetterDto]
):
    """Shared workflow engine for submit/approve/sign/dispatch/receive (§16).

    Authorization: submit = sender; approve = letter.approve; sign =
    letter.sign; dispatch = letter.dispatch; receive = recipient."""

    requiredAction = ""

    def __init__(
        self,
        letterRepository: LetterRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.letterRepository = letterRepository
        self.gate = self.permissionGate

    def perform(self, command: SubmitLetterCommand) -> LetterDto:
        actorId, tenantId = actorOf()
        letter = self.letterRepository.getById(asUuid(command.letterId), tenantId)
        if letter is None:
            raise EntityNotFoundError("OfficialLetter", command.letterId)
        action = command.action
        now = self.clock.nowUtc()
        if action == "submit":
            if letter.senderId != actorId:
                raise PermissionDeniedError(action="letter.submit")
            letter.transitionTo("IN_REVIEW", now)
        elif action == "approve":
            self.require("letter.approve", actorId, tenantId)
            letter.approve(now, actorId)
        elif action == "sign":
            self.require("letter.sign", actorId, tenantId)
            letter.sign(now, actorId)
        elif action == "dispatch":
            self.require("letter.dispatch", actorId, tenantId)
            letter.dispatch(now)
        elif action == "receive":
            if letter.recipientId != actorId:
                raise PermissionDeniedError(action="letter.receive")
            letter.markReceived(now)
        else:  # pragma: no cover — commands are typed
            raise ValidationFailedError("Unknown letter action.")
        self.letterRepository.update(letter)
        self.collectEventsFrom(letter)
        self.emitIntegrationEvent(
            tenantId,
            f"Letter{letter.letterStatus.capitalize()}",
            {"referenceNumber": letter.referenceNumber},
        )
        self.broadcastUser(
            letter.recipientId,
            {"type": "letter.updated", "referenceNumber": letter.referenceNumber},
        )
        self.audit(
            "UPDATE",
            resourceType="OfficialLetter",
            resourceId=str(letter.id),
            tenantId=tenantId,
            after={"status": letter.letterStatus, "action": action},
        )
        return letterDto(letter)

    def require(self, action: str, actorId: uuid.UUID, tenantId: uuid.UUID) -> None:
        if not self.gate.hasPermission(actorId, action, tenantId=tenantId):
            raise PermissionDeniedError(action=action)


class ListLettersUseCase(CommunicationUseCase[ListLettersQuery, list[LetterDto]]):
    requiredAction = ""

    def __init__(
        self,
        letterRepository: LetterRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.letterRepository = letterRepository

    def perform(self, query: ListLettersQuery) -> list[LetterDto]:
        _, tenantId = actorOf()
        return [
            letterDto(letter)
            for letter in self.letterRepository.list(
                tenantId, status=query.status, limit=query.limit
            )
        ]


# -- DTO helpers ----------------------------------------------------------------------


def meetingDto(meeting: Meeting, participants: list | None = None) -> MeetingDto:
    return MeetingDto(
        id=str(meeting.id),
        conversationId=str(meeting.conversationId),
        organizerId=str(meeting.organizerId),
        title=meeting.title,
        description=meeting.description,
        meetingStatus=meeting.meetingStatus,
        scheduledStart=meeting.scheduledStart.isoformat() if meeting.scheduledStart else "",
        scheduledEnd=meeting.scheduledEnd.isoformat() if meeting.scheduledEnd else "",
        actualStart=meeting.actualStart.isoformat() if meeting.actualStart else "",
        actualEnd=meeting.actualEnd.isoformat() if meeting.actualEnd else "",
        createdAt=meeting.createdAt.isoformat(),
        participants=participants or [],
    )


def recordingDto(recording: Recording) -> RecordingDto:
    return RecordingDto(
        id=str(recording.id),
        meetingId=str(recording.meetingId),
        recordingStatus=recording.recordingStatus,
        requestedBy=str(recording.requestedBy),
        startedAt=recording.startedAt.isoformat() if recording.startedAt else "",
        stoppedAt=recording.stoppedAt.isoformat() if recording.stoppedAt else "",
        durationSeconds=recording.durationSeconds,
        storageRef=recording.storageRef,
    )


def letterDto(letter: OfficialLetter) -> LetterDto:
    return LetterDto(
        id=str(letter.id),
        referenceNumber=letter.referenceNumber,
        senderId=str(letter.senderId),
        recipientId=str(letter.recipientId),
        subject=letter.subject,
        body=letter.body,
        recipientOrganization=letter.recipientOrganization,
        recipientUnit=letter.recipientUnit,
        letterStatus=letter.letterStatus,
        createdAt=letter.createdAt.isoformat(),
        approvedBy=str(letter.approvedBy) if letter.approvedBy else "",
        signedBy=str(letter.signedBy) if letter.signedBy else "",
        dispatchedAt=letter.dispatchedAt.isoformat() if letter.dispatchedAt else "",
        receivedAt=letter.receivedAt.isoformat() if letter.receivedAt else "",
    )
