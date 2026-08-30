"""Conversation use cases (Phase 08 §3.1–§3.2, §4–§6, §35).

Security model (§17): sender/actor identity always comes from the
authenticated context — never the payload; tenant comes from the context
too. Membership + role checks guard every mutation; permissions guard
admin-level operations (channel creation, moderation).
"""

from __future__ import annotations

import uuid

from apps.communication.application.commands.communicationCommands import (
    AddParticipantCommand,
    ArchiveConversationCommand,
    ChangeParticipantRoleCommand,
    CreateChannelCommand,
    CreateDirectConversationCommand,
    CreateGroupConversationCommand,
    JoinChannelCommand,
    LeaveConversationCommand,
    RemoveParticipantCommand,
    UpdateConversationCommand,
    UpdateParticipantPreferencesCommand,
)
from apps.communication.application.dto.communicationDtos import (
    ConversationDto,
    ParticipantDto,
)
from apps.communication.application.queries.communicationQueries import (
    GetConversationQuery,
    ListConversationsQuery,
    ListParticipantsQuery,
)
from apps.communication.application.services.communicationSupport import (
    CommunicationUseCase,
    UserDirectory,
)
from apps.communication.domain.entities.conversation import Conversation
from apps.communication.domain.entities.participant import ConversationParticipant
from apps.communication.domain.repositories.communicationRepositories import (
    ConversationRepository,
    ParticipantRepository,
)
from apps.communication.domain.valueObjects.communicationTypes import (
    CHANNEL_PUBLIC,
    CONVERSATION_CHANNEL,
    CONVERSATION_DIRECT,
    PARTICIPANT_ADMIN,
    PARTICIPANT_MEMBER,
    PARTICIPANT_OWNER,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import (
    AuthenticationRequiredError,
    EntityNotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


def actorOf() -> tuple[uuid.UUID, uuid.UUID]:
    """§17 — (actorId, tenantId) strictly from the authenticated context."""
    context = currentContext()
    if not context.actorId or not context.tenantId:
        raise AuthenticationRequiredError()
    return uuid.UUID(context.actorId), uuid.UUID(context.tenantId)


class CreateDirectConversationUseCase(
    CommunicationUseCase[CreateDirectConversationCommand, ConversationDto]
):
    """§5 — exactly two participants; the deterministic directKey prevents
    accidental duplicates; both users must belong to the SAME tenant."""

    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        userDirectory: UserDirectory,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.userDirectory = userDirectory

    def perform(self, command: CreateDirectConversationCommand) -> ConversationDto:
        actorId, tenantId = actorOf()
        peerId = asUuid(command.peerUserId)
        if not self.userDirectory.exists(tenantId, peerId):
            raise EntityNotFoundError("User", command.peerUserId)

        from apps.communication.domain.services.communicationRules import directKeyOf

        directKey = directKeyOf(actorId, peerId)
        existing = self.conversationRepository.getByDirectKey(tenantId, directKey)
        if existing is not None:
            return conversationDto(existing)  # §5 — idempotent by design

        now = self.clock.nowUtc()
        conversation = Conversation.createDirect(tenantId, actorId, peerId, now)
        self.conversationRepository.create(conversation)
        for userId, role in ((actorId, PARTICIPANT_OWNER), (peerId, PARTICIPANT_MEMBER)):
            self.participantRepository.add(
                ConversationParticipant.establish(
                    conversation.id, tenantId, userId, role, now
                )
            )
        self.collectEventsFrom(conversation)
        self.emitIntegrationEvent(
            tenantId,
            "ConversationCreated",
            {"conversationId": str(conversation.id), "type": CONVERSATION_DIRECT},
        )
        self.audit(
            "CREATE",
            resourceType="Conversation",
            resourceId=str(conversation.id),
            tenantId=tenantId,
            after={"type": CONVERSATION_DIRECT},
        )
        return conversationDto(conversation)


class CreateGroupConversationUseCase(
    CommunicationUseCase[CreateGroupConversationCommand, ConversationDto]
):
    """§6 — group with roles, invitations and full membership history."""

    requiredAction = "conversation.create"

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        userDirectory: UserDirectory,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.userDirectory = userDirectory

    def validateCommand(self, command: CreateGroupConversationCommand) -> None:
        if not command.name.strip():
            raise ValidationFailedError(
                "Group name is required.", fieldErrors={"name": "empty"}
            )

    def perform(self, command: CreateGroupConversationCommand) -> ConversationDto:
        actorId, tenantId = actorOf()
        now = self.clock.nowUtc()
        conversation = Conversation.createGroup(
            tenantId, actorId, command.name, now, description=command.description
        )
        self.conversationRepository.create(conversation)
        self.participantRepository.add(
            ConversationParticipant.establish(
                conversation.id, tenantId, actorId, PARTICIPANT_OWNER, now
            )
        )
        for member in command.memberIds:
            memberId = asUuid(member)
            if memberId == actorId:
                continue
            if not self.userDirectory.exists(tenantId, memberId):
                raise EntityNotFoundError("User", member)
            self.participantRepository.add(
                ConversationParticipant.establish(
                    conversation.id, tenantId, memberId, PARTICIPANT_MEMBER, now,
                    invitedBy=actorId,
                )
            )
        self.collectEventsFrom(conversation)
        self.emitIntegrationEvent(
            tenantId,
            "ConversationCreated",
            {"conversationId": str(conversation.id), "type": "GROUP"},
        )
        self.audit(
            "CREATE",
            resourceType="Conversation",
            resourceId=str(conversation.id),
            tenantId=tenantId,
            after={"name": conversation.name},
        )
        return conversationDto(conversation)


class CreateChannelUseCase(CommunicationUseCase[CreateChannelCommand, ConversationDto]):
    """§4 — public/private/restricted channels with topic and description."""

    requiredAction = "conversation.create"

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def validateCommand(self, command: CreateChannelCommand) -> None:
        if not command.name.strip():
            raise ValidationFailedError(
                "Channel name is required.", fieldErrors={"name": "empty"}
            )
        from apps.communication.domain.valueObjects.communicationTypes import (
            ChannelVisibility,
        )

        ChannelVisibility(command.visibility)

    def perform(self, command: CreateChannelCommand) -> ConversationDto:
        actorId, tenantId = actorOf()
        code = command.code.strip().lower()
        if code and self.conversationRepository.channelCodeExists(tenantId, code):
            from apps.sharedKernel.domain.errors import DuplicateIdentifierError

            raise DuplicateIdentifierError(
                "Channel code already exists in this tenant.",
                details={"ruleId": "PHASE8-UQ_Channel_code"},
            )
        now = self.clock.nowUtc()
        conversation = Conversation.createChannel(
            tenantId, actorId, command.name, now,
            description=command.description, code=code,
        )
        self.conversationRepository.create(
            conversation,
            code=code, topic=command.topic, visibility=command.visibility,
        )
        self.participantRepository.add(
            ConversationParticipant.establish(
                conversation.id, tenantId, actorId, PARTICIPANT_OWNER, now
            )
        )
        self.collectEventsFrom(conversation)
        self.emitIntegrationEvent(
            tenantId,
            "ConversationCreated",
            {"conversationId": str(conversation.id), "type": CONVERSATION_CHANNEL},
        )
        self.audit(
            "CREATE",
            resourceType="Conversation",
            resourceId=str(conversation.id),
            tenantId=tenantId,
            after={"name": conversation.name, "visibility": command.visibility},
        )
        dto = conversationDto(conversation)
        return ConversationDto(
            **{**dto.__dict__, "topic": command.topic, "visibility": command.visibility}
        )


class UpdateConversationUseCase(
    CommunicationUseCase[UpdateConversationCommand, ConversationDto]
):
    """Name/description (groups) + topic/description (channels) — admins."""

    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, command: UpdateConversationCommand) -> ConversationDto:
        actorId, tenantId = actorOf()
        conversation = self.loadConversation(command.conversationId, tenantId)
        self.requireAdmin(conversation.id, actorId)
        now = self.clock.nowUtc()
        conversation.updateProfile(
            name=command.name or None, description=command.description or None, now=now
        )
        self.conversationRepository.update(conversation)
        if conversation.conversationType == CONVERSATION_CHANNEL and command.topic:
            self.conversationRepository.updateChannelProfile(
                conversation.id,
                topic=command.topic,
                visibility=None,
                description=None,
                name=None,
            )
        self.audit(
            "UPDATE",
            resourceType="Conversation",
            resourceId=str(conversation.id),
            tenantId=tenantId,
            after={"name": conversation.name},
        )
        return conversationDto(conversation)

    # -- helpers --------------------------------------------------------------

    def loadConversation(self, conversationId: str, tenantId: uuid.UUID) -> Conversation:
        conversation = self.conversationRepository.getById(
            asUuid(conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", conversationId)
        return conversation

    def requireAdmin(self, conversationId: uuid.UUID, actorId: uuid.UUID) -> None:
        participant = self.participantRepository.get(conversationId, actorId)
        if participant is None or not participant.isAdmin() or not participant.isActive():
            raise PermissionDeniedError(action="conversation.update")


class ArchiveConversationUseCase(
    CommunicationUseCase[ArchiveConversationCommand, object]
):
    requiredAction = "conversation.moderate"

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, command: ArchiveConversationCommand) -> object:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        participant = self.participantRepository.get(conversation.id, actorId)
        if participant is None or not participant.isAdmin():
            raise PermissionDeniedError(action="conversation.archive")
        conversation.archive(self.clock.nowUtc())
        self.conversationRepository.update(conversation)
        self.collectEventsFrom(conversation)
        self.emitIntegrationEvent(
            tenantId,
            "ConversationArchived",
            {"conversationId": str(conversation.id)},
        )
        self.broadcastConversation(conversation.id, {"type": "conversation.archived"})
        self.audit(
            "ARCHIVE",
            resourceType="Conversation",
            resourceId=str(conversation.id),
            tenantId=tenantId,
        )
        return {"archived": True, "conversationId": str(conversation.id)}


class AddParticipantUseCase(CommunicationUseCase[AddParticipantCommand, ParticipantDto]):
    """§6 invitations + §38 duplicate-participant guard."""

    requiredAction = "conversation.moderate"

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        userDirectory: UserDirectory,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.userDirectory = userDirectory

    def perform(self, command: AddParticipantCommand) -> ParticipantDto:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        moderator = self.participantRepository.get(conversation.id, actorId)
        if moderator is None or not moderator.isModerator() or not moderator.isActive():
            raise PermissionDeniedError(action="participant.add")
        newUserId = asUuid(command.userId)
        if not self.userDirectory.exists(tenantId, newUserId):
            raise EntityNotFoundError("User", command.userId)
        existing = self.participantRepository.get(conversation.id, newUserId)
        now = self.clock.nowUtc()
        if existing is not None and existing.isActive():
            if existing.role == command.role:
                return participantDto(existing)  # §24 idempotent retry
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("User is already an active participant.")
        if existing is not None:  # re-join keeps history (§6)
            existing.leftAt = None
            existing.joinedAt = now
            existing.role = command.role
            self.participantRepository.update(existing)
            participant = existing
        else:
            participant = ConversationParticipant.establish(
                conversation.id, tenantId, newUserId, command.role, now, invitedBy=actorId
            )
            self.participantRepository.add(participant)
        self.collectEventsFrom(participant)
        self.emitIntegrationEvent(
            tenantId,
            "ParticipantJoined",
            {
                "conversationId": str(conversation.id),
                "userId": str(newUserId),
            },
        )
        self.broadcastConversation(
            conversation.id,
            {"type": "participant.joined", "userId": str(newUserId)},
        )
        self.audit(
            "UPDATE",
            resourceType="Conversation",
            resourceId=str(conversation.id),
            tenantId=tenantId,
            after={"addedUserId": str(newUserId)},
        )
        return participantDto(participant)


class RemoveParticipantUseCase(
    CommunicationUseCase[RemoveParticipantCommand, object]
):
    requiredAction = "conversation.moderate"

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, command: RemoveParticipantCommand) -> object:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        moderator = self.participantRepository.get(conversation.id, actorId)
        if moderator is None or not moderator.isModerator() or not moderator.isActive():
            raise PermissionDeniedError(action="participant.remove")
        target = self.participantRepository.get(conversation.id, asUuid(command.userId))
        if target is None or not target.isActive():
            raise EntityNotFoundError("Participant", command.userId)
        now = self.clock.nowUtc()
        target.remove(now, actorId)
        self.participantRepository.update(target)
        self.collectEventsFrom(target)
        self.emitIntegrationEvent(
            tenantId,
            "ParticipantLeft",
            {"conversationId": str(conversation.id), "userId": command.userId},
        )
        self.broadcastConversation(
            conversation.id, {"type": "participant.left", "userId": command.userId}
        )
        self.audit(
            "UPDATE",
            resourceType="Conversation",
            resourceId=str(conversation.id),
            tenantId=tenantId,
            after={"removedUserId": command.userId},
        )
        return {"removed": True, "userId": command.userId}


class UpdateParticipantPreferencesUseCase(
    CommunicationUseCase[UpdateParticipantPreferencesCommand, ParticipantDto]
):
    """Self-service mute/notification level (§6)."""

    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(
        self, command: UpdateParticipantPreferencesCommand
    ) -> ParticipantDto:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        participant = self.participantRepository.get(conversation.id, actorId)
        if participant is None or not participant.isActive():
            raise PermissionDeniedError(action="participant.update")
        participant.setPreferences(
            isMuted=command.isMuted,
            notificationLevel=command.notificationLevel or None,
        )
        self.participantRepository.update(participant)
        return participantDto(participant)


class JoinChannelUseCase(CommunicationUseCase[JoinChannelCommand, ParticipantDto]):
    """§4 — self-join PUBLIC channels only; PRIVATE/RESTRICTED need invite."""

    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        channelProfileReader: object,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.channelProfileReader = channelProfileReader

    def perform(self, command: JoinChannelCommand) -> ParticipantDto:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None or conversation.conversationType != CONVERSATION_CHANNEL:
            raise EntityNotFoundError("Conversation", command.conversationId)
        visibility = self.channelProfileReader.visibilityOf(conversation.id)
        if visibility != CHANNEL_PUBLIC:
            raise PermissionDeniedError(
                "Channel is not public.", action="channel.join"
            )
        existing = self.participantRepository.get(conversation.id, actorId)
        now = self.clock.nowUtc()
        if existing is not None and existing.isActive():
            return participantDto(existing)  # idempotent join
        if existing is not None:
            existing.leftAt = None
            existing.joinedAt = now
            self.participantRepository.update(existing)
            participant = existing
        else:
            participant = ConversationParticipant.establish(
                conversation.id, tenantId, actorId, PARTICIPANT_MEMBER, now
            )
            self.participantRepository.add(participant)
        self.collectEventsFrom(participant)
        self.broadcastConversation(
            conversation.id, {"type": "participant.joined", "userId": str(actorId)}
        )
        return participantDto(participant)


class ListConversationsUseCase(
    CommunicationUseCase[ListConversationsQuery, list[ConversationDto]]
):
    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, query: ListConversationsQuery) -> list[ConversationDto]:
        actorId, tenantId = actorOf()
        summaries = self.conversationRepository.listForUser(
            tenantId, actorId, includeArchived=query.includeArchived
        )
        return [
            ConversationDto(
                id=str(s.id),
                tenantId=str(s.tenantId),
                type=s.conversationType,
                name=s.name,
                description=s.description,
                topic=s.topic,
                visibility=s.visibility,
                isActive=s.isActive,
                archivedAt=s.archivedAt.isoformat() if s.archivedAt else "",
                createdAt=s.createdAt.isoformat(),
                lastMessageAt=s.lastMessageAt.isoformat() if s.lastMessageAt else "",
                lastMessagePreview=s.lastMessagePreview,
                unreadCount=s.unreadCount,
            )
            for s in summaries
        ]


class GetConversationUseCase(
    CommunicationUseCase[GetConversationQuery, ConversationDto]
):
    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        channelProfileReader: object = None,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.channelProfileReader = channelProfileReader

    def perform(self, query: GetConversationQuery) -> ConversationDto:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(query.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", query.conversationId)
        if conversation.conversationType != CONVERSATION_CHANNEL:
            participant = self.participantRepository.get(conversation.id, actorId)
            if participant is None or not participant.isActive():
                raise PermissionDeniedError(action="conversation.view")
        dto = conversationDto(conversation)
        if conversation.conversationType == CONVERSATION_CHANNEL and self.channelProfileReader:
            topic, visibility = self.channelProfileReader.profileOf(conversation.id)
            dto = ConversationDto(**{**dto.__dict__, "topic": topic, "visibility": visibility})
        return dto


class ListParticipantsUseCase(
    CommunicationUseCase[ListParticipantsQuery, list[ParticipantDto]]
):
    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, query: ListParticipantsQuery) -> list[ParticipantDto]:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(query.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", query.conversationId)
        if conversation.conversationType != CONVERSATION_CHANNEL:
            me = self.participantRepository.get(conversation.id, actorId)
            if me is None or not me.isActive():
                raise PermissionDeniedError(action="participant.list")
        return [
            participantDto(p)
            for p in self.participantRepository.listForConversation(conversation.id)
        ]


def conversationDto(conversation: Conversation) -> ConversationDto:
    return ConversationDto(
        id=str(conversation.id),
        tenantId=str(conversation.tenantId),
        type=conversation.conversationType,
        name=conversation.name,
        description=conversation.description,
        isActive=conversation.isActive,
        archivedAt=conversation.archivedAt.isoformat() if conversation.archivedAt else "",
        createdAt=conversation.createdAt.isoformat(),
    )


def participantDto(participant: ConversationParticipant) -> ParticipantDto:
    return ParticipantDto(
        id=str(participant.id),
        conversationId=str(participant.conversationId),
        userId=str(participant.userId),
        role=participant.role,
        joinedAt=participant.joinedAt.isoformat(),
        leftAt=participant.leftAt.isoformat() if participant.leftAt else "",
        isMuted=participant.isMuted,
        notificationLevel=participant.notificationLevel,
        isActive=participant.isActive(),
    )


class LeaveConversationUseCase(
    CommunicationUseCase[LeaveConversationCommand, object]
):
    """§6 — members may leave; the owner must transfer ownership first."""

    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, command: LeaveConversationCommand) -> object:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        me = self.participantRepository.get(conversation.id, actorId)
        if me is None or not me.isActive():
            raise EntityNotFoundError("Participant", str(actorId))
        me.leave(self.clock.nowUtc())
        self.participantRepository.update(me)
        self.collectEventsFrom(me)
        self.emitIntegrationEvent(
            tenantId,
            "ParticipantLeft",
            {"conversationId": str(conversation.id), "userId": str(actorId)},
        )
        self.broadcastConversation(
            conversation.id,
            {"type": "participant.left", "userId": str(actorId)},
        )
        self.audit(
            "UPDATE",
            resourceType="ConversationParticipant",
            resourceId=str(me.id),
            tenantId=tenantId,
        )
        return {"left": True, "conversationId": str(conversation.id)}


class ChangeParticipantRoleUseCase(
    CommunicationUseCase[ChangeParticipantRoleCommand, ParticipantDto]
):
    """§3.2 — moderators adjust roles; ownership transfer is refused."""

    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository

    def perform(self, command: ChangeParticipantRoleCommand) -> ParticipantDto:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        actor = self.participantRepository.get(conversation.id, actorId)
        if (
            actor is None
            or not actor.isActive()
            or not actor.isModerator()
        ):
            raise PermissionDeniedError(action="participant.changeRole")
        target = self.participantRepository.get(
            conversation.id, asUuid(command.userId)
        )
        if target is None:
            raise EntityNotFoundError("Participant", command.userId)
        target.changeRole(command.role, self.clock.nowUtc())
        self.participantRepository.update(target)
        self.emitIntegrationEvent(
            tenantId,
            "ParticipantRoleChanged",
            {
                "conversationId": str(conversation.id),
                "userId": str(target.userId),
                "role": target.role,
            },
        )
        self.audit(
            "UPDATE",
            resourceType="ConversationParticipant",
            resourceId=str(target.id),
            tenantId=tenantId,
            before={"role": "…"},
            after={"role": target.role},
        )
        return participantDto(target)
