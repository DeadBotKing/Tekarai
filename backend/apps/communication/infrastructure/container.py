"""Communication composition root (Phase 08 §35 services)."""

from __future__ import annotations

from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


def kernelPorts() -> dict:
    return {
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


# -- singletons shared by every communication use case ----------------------------


def commPorts() -> dict:
    ports = kernelPorts()
    ports["outboxRepository"] = outboxRepository()
    ports["realtime"] = broadcaster()
    return ports


_broadcasterSingleton = None


def broadcaster():
    global _broadcasterSingleton
    if _broadcasterSingleton is None:
        from apps.communication.infrastructure.realtime.realtimeInfra import (
            ChannelsRealtimeBroadcaster,
        )

        _broadcasterSingleton = ChannelsRealtimeBroadcaster()
    return _broadcasterSingleton


_presenceSingleton = None


def presenceRepository():
    global _presenceSingleton
    if _presenceSingleton is None:
        from apps.communication.infrastructure.realtime.realtimeInfra import (
            RedisPresenceRepository,
        )

        _presenceSingleton = RedisPresenceRepository()
    return _presenceSingleton


def mediaRouter():
    from apps.communication.infrastructure.realtime.realtimeInfra import NoopMediaRouter

    return NoopMediaRouter()


def userDirectory():
    from apps.communication.infrastructure.services.userDirectoryImpl import (
        UserDirectoryOverIdentity,
    )

    return UserDirectoryOverIdentity()


def transcriptReader():
    from apps.communication.infrastructure.services.aiServicesImpl import (
        TranscriptReaderDjango,
    )

    return TranscriptReaderDjango()


def aiAssistant():
    from apps.communication.infrastructure.services.aiServicesImpl import (
        LocalMeetingAiAssistant,
    )

    return LocalMeetingAiAssistant()


# -- repositories --------------------------------------------------------------------


def conversationRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        ConversationRepositoryDjango,
    )

    return ConversationRepositoryDjango()


def channelProfileReader():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        ChannelProfileReader,
    )

    return ChannelProfileReader()


def participantRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        ParticipantRepositoryDjango,
    )

    return ParticipantRepositoryDjango()


def messageRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        MessageRepositoryDjango,
    )

    return MessageRepositoryDjango()


def attachmentRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        AttachmentRepositoryDjango,
    )

    return AttachmentRepositoryDjango()


def reactionRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        ReactionRepositoryDjango,
    )

    return ReactionRepositoryDjango()


def readStateRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        ReadStateRepositoryDjango,
    )

    return ReadStateRepositoryDjango()


def pinRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        PinRepositoryDjango,
    )

    return PinRepositoryDjango()


def meetingRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        MeetingRepositoryDjango,
    )

    return MeetingRepositoryDjango()


def meetingParticipantRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        MeetingParticipantRepositoryDjango,
    )

    return MeetingParticipantRepositoryDjango()


def callRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        CallRepositoryDjango,
    )

    return CallRepositoryDjango()


def callParticipantRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        CallParticipantRepositoryDjango,
    )

    return CallParticipantRepositoryDjango()


def recordingRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        RecordingRepositoryDjango,
    )

    return RecordingRepositoryDjango()


def letterRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        LetterRepositoryDjango,
    )

    return LetterRepositoryDjango()


# -- conversations -------------------------------------------------------------------


def createDirectUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        CreateDirectConversationUseCase,
    )

    return CreateDirectConversationUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        userDirectory=userDirectory(),
        **commPorts(),
    )


def createGroupUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        CreateGroupConversationUseCase,
    )

    return CreateGroupConversationUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        userDirectory=userDirectory(),
        **commPorts(),
    )


def createChannelUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        CreateChannelUseCase,
    )

    return CreateChannelUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def updateConversationUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        UpdateConversationUseCase,
    )

    return UpdateConversationUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def archiveConversationUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        ArchiveConversationUseCase,
    )

    return ArchiveConversationUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def addParticipantUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        AddParticipantUseCase,
    )

    return AddParticipantUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        userDirectory=userDirectory(),
        **commPorts(),
    )


def removeParticipantUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        RemoveParticipantUseCase,
    )

    return RemoveParticipantUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def leaveConversationUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        LeaveConversationUseCase,
    )

    return LeaveConversationUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def updateParticipantPreferencesUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        UpdateParticipantPreferencesUseCase,
    )

    return UpdateParticipantPreferencesUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def changeParticipantRoleUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        ChangeParticipantRoleUseCase,
    )

    return ChangeParticipantRoleUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def joinChannelUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        JoinChannelUseCase,
    )

    return JoinChannelUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        channelProfileReader=channelProfileReader(),
        **commPorts(),
    )


def listConversationsUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        ListConversationsUseCase,
    )

    return ListConversationsUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def getConversationUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        GetConversationUseCase,
    )

    return GetConversationUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        channelProfileReader=channelProfileReader(),
        **commPorts(),
    )


def listParticipantsUseCase():
    from apps.communication.application.useCases.conversationUseCases import (
        ListParticipantsUseCase,
    )

    return ListParticipantsUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


# -- messages ------------------------------------------------------------------------


def sendMessageUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        SendMessageUseCase,
    )

    return SendMessageUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        messageRepository=messageRepository(),
        attachmentRepository=attachmentRepository(),
        readStateRepository=readStateRepository(),
        userDirectory=userDirectory(),
        **commPorts(),
    )


def editMessageUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        EditMessageUseCase,
    )

    return EditMessageUseCase(
        messageRepository=messageRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def deleteMessageUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        DeleteMessageUseCase,
    )

    return DeleteMessageUseCase(
        messageRepository=messageRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def reactToMessageUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        ReactToMessageUseCase,
    )

    return ReactToMessageUseCase(
        messageRepository=messageRepository(),
        reactionRepository=reactionRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def removeReactionUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        RemoveReactionUseCase,
    )

    return RemoveReactionUseCase(
        messageRepository=messageRepository(),
        reactionRepository=reactionRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def markConversationReadUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        MarkConversationReadUseCase,
    )

    return MarkConversationReadUseCase(
        conversationRepository=conversationRepository(),
        messageRepository=messageRepository(),
        participantRepository=participantRepository(),
        readStateRepository=readStateRepository(),
        **commPorts(),
    )


def pinMessageUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        PinMessageUseCase,
    )

    return PinMessageUseCase(
        conversationRepository=conversationRepository(),
        messageRepository=messageRepository(),
        participantRepository=participantRepository(),
        pinRepository=pinRepository(),
        **commPorts(),
    )


def unpinMessageUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        UnpinMessageUseCase,
    )

    return UnpinMessageUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        pinRepository=pinRepository(),
        **commPorts(),
    )


def listMessagesUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        ListMessagesUseCase,
    )

    return ListMessagesUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        messageRepository=messageRepository(),
        reactionRepository=reactionRepository(),
        attachmentRepository=attachmentRepository(),
        **commPorts(),
    )


def searchMessagesUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        SearchMessagesUseCase,
    )

    return SearchMessagesUseCase(
        messageRepository=messageRepository(),
        **commPorts(),
    )


def listPinsUseCase():
    from apps.communication.application.useCases.messageUseCases import (
        ListPinsUseCase,
    )

    return ListPinsUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        pinRepository=pinRepository(),
        **commPorts(),
    )


# -- meetings & recordings -------------------------------------------------------------


def createMeetingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        CreateMeetingUseCase,
    )

    return CreateMeetingUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        meetingRepository=meetingRepository(),
        meetingParticipantRepository=meetingParticipantRepository(),
        userDirectory=userDirectory(),
        **commPorts(),
    )


def startMeetingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        StartMeetingUseCase,
    )

    return StartMeetingUseCase(
        meetingRepository=meetingRepository(),
        **commPorts(),
    )


def joinMeetingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        JoinMeetingUseCase,
    )

    return JoinMeetingUseCase(
        meetingRepository=meetingRepository(),
        meetingParticipantRepository=meetingParticipantRepository(),
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def leaveMeetingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        LeaveMeetingUseCase,
    )

    return LeaveMeetingUseCase(
        meetingRepository=meetingRepository(),
        meetingParticipantRepository=meetingParticipantRepository(),
        **commPorts(),
    )


def rsvpMeetingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        RsvpMeetingUseCase,
    )

    return RsvpMeetingUseCase(
        meetingRepository=meetingRepository(),
        meetingParticipantRepository=meetingParticipantRepository(),
        **commPorts(),
    )


def endMeetingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        EndMeetingUseCase,
    )

    return EndMeetingUseCase(
        meetingRepository=meetingRepository(),
        recordingRepository=recordingRepository(),
        meetingParticipantRepository=meetingParticipantRepository(),
        **commPorts(),
    )


def cancelMeetingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        CancelMeetingUseCase,
    )

    return CancelMeetingUseCase(
        meetingRepository=meetingRepository(),
        **commPorts(),
    )


def listMeetingsUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        ListMeetingsUseCase,
    )

    return ListMeetingsUseCase(
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        meetingRepository=meetingRepository(),
        meetingParticipantRepository=meetingParticipantRepository(),
        **commPorts(),
    )


def getMeetingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        GetMeetingUseCase,
    )

    return GetMeetingUseCase(
        meetingRepository=meetingRepository(),
        meetingParticipantRepository=meetingParticipantRepository(),
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def startRecordingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        StartRecordingUseCase,
    )

    return StartRecordingUseCase(
        meetingRepository=meetingRepository(),
        recordingRepository=recordingRepository(),
        **commPorts(),
    )


def stopRecordingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        StopRecordingUseCase,
    )

    return StopRecordingUseCase(
        recordingRepository=recordingRepository(),
        **commPorts(),
    )


def publishRecordingUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        PublishRecordingUseCase,
    )

    return PublishRecordingUseCase(
        recordingRepository=recordingRepository(),
        **commPorts(),
    )


def listRecordingsUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        ListRecordingsUseCase,
    )

    return ListRecordingsUseCase(
        meetingRepository=meetingRepository(),
        recordingRepository=recordingRepository(),
        **commPorts(),
    )


# -- letters (§16) ----------------------------------------------------------------------


def createLetterUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        CreateLetterUseCase,
    )

    return CreateLetterUseCase(
        letterRepository=letterRepository(),
        userDirectory=userDirectory(),
        **commPorts(),
    )


def letterTransitionUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        LetterTransitionUseCase,
    )

    return LetterTransitionUseCase(
        letterRepository=letterRepository(),
        **commPorts(),
    )


def listLettersUseCase():
    from apps.communication.application.useCases.meetingUseCases import (
        ListLettersUseCase,
    )

    return ListLettersUseCase(
        letterRepository=letterRepository(),
        **commPorts(),
    )


# -- calls & signaling (§10–§14) ---------------------------------------------------------


def startCallUseCase():
    from apps.communication.application.useCases.callUseCases import (
        StartCallUseCase,
    )

    return StartCallUseCase(
        callRepository=callRepository(),
        callParticipantRepository=callParticipantRepository(),
        conversationRepository=conversationRepository(),
        meetingRepository=meetingRepository(),
        participantRepository=participantRepository(),
        mediaRouter=mediaRouter(),
        **commPorts(),
    )


def acceptCallUseCase():
    from apps.communication.application.useCases.callUseCases import (
        AcceptCallUseCase,
    )

    return AcceptCallUseCase(
        callRepository=callRepository(),
        callParticipantRepository=callParticipantRepository(),
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        mediaRouter=mediaRouter(),
        **commPorts(),
    )


def rejectCallUseCase():
    from apps.communication.application.useCases.callUseCases import (
        RejectCallUseCase,
    )

    return RejectCallUseCase(
        callRepository=callRepository(),
        callParticipantRepository=callParticipantRepository(),
        conversationRepository=conversationRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def endCallUseCase():
    from apps.communication.application.useCases.callUseCases import (
        EndCallUseCase,
    )

    return EndCallUseCase(
        callRepository=callRepository(),
        callParticipantRepository=callParticipantRepository(),
        mediaRouter=mediaRouter(),
        **commPorts(),
    )


def relaySignalUseCase():
    from apps.communication.application.useCases.callUseCases import (
        RelaySignalUseCase,
    )

    return RelaySignalUseCase(
        callRepository=callRepository(),
        callParticipantRepository=callParticipantRepository(),
        **commPorts(),
    )


def getCallUseCase():
    from apps.communication.application.useCases.callUseCases import (
        GetCallUseCase,
    )

    return GetCallUseCase(
        callRepository=callRepository(),
        callParticipantRepository=callParticipantRepository(),
        **commPorts(),
    )


# -- presence & AI (§7/§21) ---------------------------------------------------------------


def updatePresenceUseCase():
    from apps.communication.application.useCases.presenceAndAiUseCases import (
        UpdatePresenceUseCase,
    )

    return UpdatePresenceUseCase(
        presenceRepository=presenceRepository(),
        participantRepository=participantRepository(),
        **commPorts(),
    )


def getPresenceUseCase():
    from apps.communication.application.useCases.presenceAndAiUseCases import (
        GetPresenceUseCase,
    )

    return GetPresenceUseCase(
        presenceRepository=presenceRepository(),
        **commPorts(),
    )


def generateMeetingSummaryUseCase():
    from apps.communication.application.useCases.presenceAndAiUseCases import (
        GenerateMeetingSummaryUseCase,
    )

    return GenerateMeetingSummaryUseCase(
        meetingRepository=meetingRepository(),
        meetingParticipantRepository=meetingParticipantRepository(),
        transcriptReader=transcriptReader(),
        aiAssistant=aiAssistant(),
        **commPorts(),
    )


def realtimeRelayService():
    from apps.communication.application.useCases.presenceAndAiUseCases import (
        RealtimeRelayService,
    )

    return RealtimeRelayService(
        participantRepository=participantRepository(),
        presenceRepository=presenceRepository(),
        realtime=broadcaster(),
    )


def outboxDispatcher():
    from apps.communication.infrastructure.realtime.realtimeInfra import (
        OutboxDispatcher,
    )

    ports = kernelPorts()
    return OutboxDispatcher(
        outboxRepository=outboxRepository(),
        eventDispatcher=ports["eventDispatcher"],
        clock=ports["clock"],
    )


def outboxRepository():
    from apps.communication.infrastructure.repositories.communicationRepositoriesImpl import (
        OutboxRepositoryDjango,
    )

    return OutboxRepositoryDjango()
