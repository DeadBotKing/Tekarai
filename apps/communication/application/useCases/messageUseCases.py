"""Message use cases (Phase 08 §3.3–§3.8, §22–§24, §32–§34).

SendMessage implements the §28 transaction recipe: authenticate → tenant →
conversation → membership → message → persist → event → commit → publish.
The §24 ``clientRequestId`` makes offline retries safe: the same request
returns the original message instead of duplicating it.
"""

from __future__ import annotations

import uuid

from apps.communication.application.commands.communicationCommands import (
    DeleteMessageCommand,
    EditMessageCommand,
    MarkConversationReadCommand,
    PinMessageCommand,
    ReactToMessageCommand,
    RemoveReactionCommand,
    SendMessageCommand,
    UnpinMessageCommand,
)
from apps.communication.application.dto.communicationDtos import (
    AttachmentDto,
    MessageDto,
    MessagePageDto,
    PinDto,
    ReactionDto,
    messageDtoFromDomain,
)
from apps.communication.application.queries.communicationQueries import (
    ListMessagesQuery,
    ListPinsQuery,
    SearchMessagesQuery,
)
from apps.communication.application.services.communicationSupport import (
    CommunicationUseCase,
    UserDirectory,
)
from apps.communication.application.useCases.conversationUseCases import actorOf
from apps.communication.domain.entities.message import (
    Message,
    MessageAttachment,
    MessageReaction,
    PinnedMessage,
)
from apps.communication.domain.repositories.communicationRepositories import (
    AttachmentRepository,
    ConversationRepository,
    MessageRepository,
    ParticipantRepository,
    PinRepository,
    ReactionRepository,
    ReadStateRepository,
)
from apps.communication.domain.services import communicationRules
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    PermissionDeniedError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid

EDIT_WINDOW_MINUTES = 15  # §33 — mirrored from settings via container default


class SendMessageUseCase(CommunicationUseCase[SendMessageCommand, MessageDto]):
    """§28 ten-step service; §17 sender identity from context only."""

    requiredAction = ""  # membership is the guard (§17), not a global action

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        messageRepository: MessageRepository,
        attachmentRepository: AttachmentRepository,
        readStateRepository: ReadStateRepository,
        userDirectory: UserDirectory,
        blockRepository: object = None,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.messageRepository = messageRepository
        self.attachmentRepository = attachmentRepository
        self.readStateRepository = readStateRepository
        self.userDirectory = userDirectory
        # Phase 10 §70 — optional block guard (direct messages); injected by
        # the container, absent in bare Phase-08 callers (behaviour unchanged).
        self.blockRepository = blockRepository

    def perform(self, command: SendMessageCommand) -> MessageDto:
        self.noteSendStarted()  # §39 messageDeliveryLatency
        senderId, tenantId = actorOf()  # §17 — never trust payload identity

        # §24 idempotency: a retry returns the original message
        if command.clientRequestId:
            existing = self.messageRepository.findByIdempotencyKey(
                tenantId,
                asUuid(command.conversationId),
                senderId,
                command.clientRequestId,
            )
            if existing is not None:
                return messageDtoFromDomain(existing)

        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None or not conversation.isActive:
            raise EntityNotFoundError("Conversation", command.conversationId)
        participant = self.participantRepository.get(conversation.id, senderId)
        if participant is None or not participant.isActive():
            raise PermissionDeniedError(action="message.send")

        # Phase 10 §70 — direct conversations honour user blocks (either side).
        if self.blockRepository is not None and conversation.conversationType == "DIRECT":
            from apps.communication.application.useCases.phase10UseCases import (
                assertNotBlocked,
            )
            from apps.communication.domain.valueObjects.phase10Types import (
                BLOCK_DIRECT_MESSAGE,
            )

            peerIds = [
                pid
                for pid in self.participantRepository.activeUserIdsOf(conversation.id)
                if pid != senderId
            ]
            for peerId in peerIds:
                assertNotBlocked(
                    self.blockRepository,
                    tenantId,
                    senderId,
                    peerId,
                    BLOCK_DIRECT_MESSAGE,
                )

        replyToId = asUuid(command.replyToId) if command.replyToId else None
        if replyToId is not None:
            root = self.messageRepository.getById(replyToId, tenantId)
            communicationRules.validateThread(
                replyToId=replyToId,
                rootFound=root is not None,
                rootSameConversation=(
                    root is not None and root.conversationId == conversation.id
                ),
            )

        mentionedIds = self._resolveMentions(command.body, tenantId)

        now = self.clock.nowUtc()
        message = Message.send(
            tenantId=tenantId,
            conversationId=conversation.id,
            senderId=senderId,
            body=command.body,
            now=now,
            messageType=command.messageType,
            replyToId=replyToId,
            clientRequestId=command.clientRequestId,
            mentions=mentionedIds,
        )
        self.messageRepository.create(message)
        for meta in command.attachments:
            self.attachmentRepository.add(
                MessageAttachment(
                    id=uuid.uuid4(),
                    tenantId=tenantId,
                    messageId=message.id,
                    fileName=str(meta.get("fileName", "file")),
                    mimeType=str(meta.get("mimeType", "application/octet-stream")),
                    sizeBytes=int(meta.get("sizeBytes", 0)),
                    createdAt=now,
                    documentRef=str(meta.get("documentRef", "")),
                )
            )
        self.collectEventsFrom(message)

        # §32 — everyone currently connected gets DELIVERED on the read state
        self.readStateRepository.markDelivered(
            tenantId,
            conversation.id,
            self.participantRepository.activeUserIdsOf(conversation.id),
            now,
        )

        self.emitIntegrationEvent(
            tenantId,
            "MessageCreated",
            {
                "conversationId": str(conversation.id),
                "messageId": str(message.id),
                "senderId": str(senderId),
                "messageType": message.messageType,
            },
        )
        # §20 notifications consume the event; mentioned users get a push
        for mentioned in mentionedIds:
            self.broadcastUser(
                uuid.UUID(mentioned),
                {"type": "notification.mention", "messageId": str(message.id)},
            )
        self.broadcastConversation(
            conversation.id, {"type": "message.created", "messageId": str(message.id)}
        )
        self.noteSendDelivered()  # §39
        self.audit(
            "CREATE",
            resourceType="Message",
            resourceId=str(message.id),
            tenantId=tenantId,
            after={
                "conversationId": str(conversation.id),
                "messageType": message.messageType,
            },
        )
        return messageDtoFromDomain(
            message,
            attachments=[
                AttachmentDto(
                    id="",
                    fileName=str(a.get("fileName", "file")),
                    mimeType=str(a.get("mimeType", "application/octet-stream")),
                    sizeBytes=int(a.get("sizeBytes", 0)),
                    documentRef=str(a.get("documentRef", "")),
                )
                for a in command.attachments
            ],
        )

    def _resolveMentions(self, body: str, tenantId: uuid.UUID) -> tuple[str, ...]:
        ids: list[str] = []
        for username in communicationRules.mentionedUsernames(body):
            userId = self.userDirectory.idOfUsername(tenantId, username)
            if userId is not None:
                ids.append(str(userId))
        return tuple(ids)


class EditMessageUseCase(CommunicationUseCase[EditMessageCommand, MessageDto]):
    """§33 — explicit policy: own message within the window; moderators."""

    requiredAction = ""

    def __init__(
        self,
        messageRepository: MessageRepository,
        participantRepository: ParticipantRepository,
        revisionRepository: object = None,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.messageRepository = messageRepository
        self.participantRepository = participantRepository
        # Phase 10 §11 — optional revision history repository (injected by the
        # container when present; absent in Phase-08 callers, so behaviour for
        # them is unchanged).
        self.revisionRepository = revisionRepository

    def perform(self, command: EditMessageCommand) -> MessageDto:
        actorId, tenantId = actorOf()
        message = self.messageRepository.getById(asUuid(command.messageId), tenantId)
        if message is None:
            raise EntityNotFoundError("Message", command.messageId)
        participant = self.participantRepository.get(message.conversationId, actorId)
        isModerator = (
            participant is not None
            and participant.isModerator()
            and participant.isActive()
        )
        allowed, reason = communicationRules.canEditMessage(
            senderId=message.senderId,
            actorId=actorId,
            createdAt=message.createdAt,
            now=self.clock.nowUtc(),
            isModerator=isModerator,
            editWindowMinutes=EDIT_WINDOW_MINUTES,
        )
        if not allowed:
            raise PermissionDeniedError(
                f"Message edit refused ({reason}).", action="message.edit"
            )
        now = self.clock.nowUtc()
        previousBody = message.body
        message.edit(command.body, now)
        self.messageRepository.update(message)
        # Phase 10 §11 — keep an immutable revision row for compliance/audit.
        if self.revisionRepository is not None and previousBody != command.body:
            from apps.communication.domain.entities.phase10Records import (
                MessageRevision,
            )

            revisionNumber = self.revisionRepository.nextRevisionNumber(
                tenantId, message.id
            )
            revision = MessageRevision.record(
                tenantId=tenantId,
                messageId=message.id,
                conversationId=message.conversationId,
                previousBody=previousBody,
                newBody=command.body,
                editedBy=actorId,
                now=now,
                revisionNumber=revisionNumber,
            )
            self.revisionRepository.add(revision)
        self.collectEventsFrom(message)
        self.emitIntegrationEvent(
            tenantId,
            "MessageEdited",
            {"messageId": str(message.id)},
        )
        self.broadcastConversation(
            message.conversationId, {"type": "message.edited", "messageId": str(message.id)}
        )
        self.audit(
            "UPDATE",
            resourceType="Message",
            resourceId=str(message.id),
            tenantId=tenantId,
            after={"edited": True},
        )
        return messageDtoFromDomain(message)


class DeleteMessageUseCase(CommunicationUseCase[DeleteMessageCommand, object]):
    """§34 — soft delete; sender owns own messages, moderators any."""

    requiredAction = ""

    def __init__(
        self,
        messageRepository: MessageRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.messageRepository = messageRepository
        self.participantRepository = participantRepository

    def perform(self, command: DeleteMessageCommand) -> object:
        actorId, tenantId = actorOf()
        message = self.messageRepository.getById(asUuid(command.messageId), tenantId)
        if message is None:
            raise EntityNotFoundError("Message", command.messageId)
        participant = self.participantRepository.get(message.conversationId, actorId)
        isModerator = (
            participant is not None
            and participant.isModerator()
            and participant.isActive()
        )
        if not communicationRules.canDeleteMessage(
            senderId=message.senderId, actorId=actorId, isModerator=isModerator
        ):
            raise PermissionDeniedError(action="message.delete")
        message.delete(self.clock.nowUtc())
        self.messageRepository.update(message)
        self.collectEventsFrom(message)
        self.emitIntegrationEvent(
            tenantId, "MessageDeleted", {"messageId": str(message.id)}
        )
        self.broadcastConversation(
            message.conversationId, {"type": "message.deleted", "messageId": str(message.id)}
        )
        self.audit(
            "DELETE",
            resourceType="Message",
            resourceId=str(message.id),
            tenantId=tenantId,
        )
        return {"deleted": True, "messageId": str(message.id)}


class ReactToMessageUseCase(CommunicationUseCase[ReactToMessageCommand, object]):
    """§3.5 — (message, user, reaction) unique; identical reaction toggles."""

    requiredAction = ""

    def __init__(
        self,
        messageRepository: MessageRepository,
        reactionRepository: ReactionRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.messageRepository = messageRepository
        self.reactionRepository = reactionRepository
        self.participantRepository = participantRepository

    def perform(self, command: ReactToMessageCommand) -> object:
        actorId, tenantId = actorOf()
        message = self.messageRepository.getById(asUuid(command.messageId), tenantId)
        if message is None:
            raise EntityNotFoundError("Message", command.messageId)
        participant = self.participantRepository.get(message.conversationId, actorId)
        if participant is None or not participant.isActive():
            raise PermissionDeniedError(action="message.react")
        if self.reactionRepository.exists(message.id, actorId, command.reaction):
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Identical reaction already exists.")  # §3.5
        reaction = MessageReaction(
            id=uuid.uuid4(),
            tenantId=tenantId,
            messageId=message.id,
            userId=actorId,
            reaction=command.reaction,
            createdAt=self.clock.nowUtc(),
        )
        self.reactionRepository.add(reaction)
        self.broadcastConversation(
            message.conversationId,
            {
                "type": "message.reactionAdded",
                "messageId": str(message.id),
                "userId": str(actorId),
                "reaction": command.reaction,
            },
        )
        return {"reacted": True, "messageId": str(message.id)}


class RemoveReactionUseCase(CommunicationUseCase[RemoveReactionCommand, object]):
    requiredAction = ""

    def __init__(
        self,
        messageRepository: MessageRepository,
        reactionRepository: ReactionRepository,
        participantRepository: ParticipantRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.messageRepository = messageRepository
        self.reactionRepository = reactionRepository
        self.participantRepository = participantRepository

    def perform(self, command: RemoveReactionCommand) -> object:
        actorId, tenantId = actorOf()
        message = self.messageRepository.getById(asUuid(command.messageId), tenantId)
        if message is None:
            raise EntityNotFoundError("Message", command.messageId)
        removed = self.reactionRepository.remove(
            message.id, actorId, command.reaction
        )
        if not removed:
            raise EntityNotFoundError("Reaction", command.reaction)
        self.broadcastConversation(
            message.conversationId,
            {
                "type": "message.reactionRemoved",
                "messageId": str(message.id),
                "userId": str(actorId),
                "reaction": command.reaction,
            },
        )
        return {"removed": True}


class MarkConversationReadUseCase(
    CommunicationUseCase[MarkConversationReadCommand, object]
):
    """§32 — bulk read receipts (one statement, no per-message writes)."""

    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        messageRepository: MessageRepository,
        participantRepository: ParticipantRepository,
        readStateRepository: ReadStateRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.messageRepository = messageRepository
        self.participantRepository = participantRepository
        self.readStateRepository = readStateRepository

    def perform(self, command: MarkConversationReadCommand) -> object:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        participant = self.participantRepository.get(conversation.id, actorId)
        if participant is None or not participant.isActive():
            raise PermissionDeniedError(action="message.read")
        uptoId = asUuid(command.uptoMessageId)
        upto = self.messageRepository.getById(uptoId, tenantId)
        if upto is None or upto.conversationId != conversation.id:
            raise EntityNotFoundError("Message", command.uptoMessageId)
        now = self.clock.nowUtc()
        updated = self.readStateRepository.markConversationRead(
            tenantId, conversation.id, actorId, upto.id, now
        )
        participant.markRead(upto.id)  # watermark for unread counts
        self.participantRepository.update(participant)
        # §9 catalogue — consumable by notify/AI/Analytics/Search/IntegrationHub
        self.emitIntegrationEvent(
            tenantId,
            "MessageRead",
            {
                "conversationId": str(conversation.id),
                "userId": str(actorId),
                "uptoMessageId": str(upto.id),
                "messagesUpdated": updated,
            },
        )
        self.broadcastConversation(
            conversation.id,
            {
                "type": "message.read",
                "userId": str(actorId),
                "uptoMessageId": str(upto.id),
            },
        )
        return {"read": True, "messagesUpdated": updated}


class PinMessageUseCase(CommunicationUseCase[PinMessageCommand, PinDto]):
    """§4 — moderators pin; one pin per message per conversation."""

    requiredAction = "conversation.moderate"

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        messageRepository: MessageRepository,
        participantRepository: ParticipantRepository,
        pinRepository: PinRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.messageRepository = messageRepository
        self.participantRepository = participantRepository
        self.pinRepository = pinRepository

    def perform(self, command: PinMessageCommand) -> PinDto:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        participant = self.participantRepository.get(conversation.id, actorId)
        if participant is None or not participant.isModerator() or not participant.isActive():
            raise PermissionDeniedError(action="message.pin")
        message = self.messageRepository.getById(asUuid(command.messageId), tenantId)
        if message is None or message.conversationId != conversation.id:
            raise EntityNotFoundError("Message", command.messageId)
        if self.pinRepository.isPinned(conversation.id, message.id):
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Message is already pinned.")
        now = self.clock.nowUtc()
        pin = PinnedMessage(
            id=uuid.uuid4(),
            tenantId=tenantId,
            conversationId=conversation.id,
            messageId=message.id,
            pinnedBy=actorId,
            pinnedAt=now,
        )
        self.pinRepository.pin(pin)
        self.broadcastConversation(
            conversation.id,
            {"type": "message.pinned", "messageId": str(message.id)},
        )
        self.audit(
            "UPDATE",
            resourceType="Conversation",
            resourceId=str(conversation.id),
            tenantId=tenantId,
            after={"pinnedMessageId": str(message.id)},
        )
        return PinDto(
            messageId=str(message.id),
            conversationId=str(conversation.id),
            pinnedBy=str(actorId),
            pinnedAt=now.isoformat(),
        )


class UnpinMessageUseCase(CommunicationUseCase[UnpinMessageCommand, object]):
    requiredAction = "conversation.moderate"

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        pinRepository: PinRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.pinRepository = pinRepository

    def perform(self, command: UnpinMessageCommand) -> object:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(command.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", command.conversationId)
        participant = self.participantRepository.get(conversation.id, actorId)
        if participant is None or not participant.isModerator() or not participant.isActive():
            raise PermissionDeniedError(action="message.unpin")
        removed = self.pinRepository.unpin(conversation.id, asUuid(command.messageId))
        if not removed:
            raise EntityNotFoundError("Pin", command.messageId)
        self.broadcastConversation(
            conversation.id,
            {"type": "message.unpinned", "messageId": command.messageId},
        )
        return {"unpinned": True}


class ListMessagesUseCase(CommunicationUseCase[ListMessagesQuery, MessagePageDto]):
    """§30 — message history with cursor pagination + thread filtering."""

    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        messageRepository: MessageRepository,
        reactionRepository: ReactionRepository,
        attachmentRepository: AttachmentRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.messageRepository = messageRepository
        self.reactionRepository = reactionRepository
        self.attachmentRepository = attachmentRepository

    def perform(self, query: ListMessagesQuery) -> MessagePageDto:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(query.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", query.conversationId)
        if conversation.conversationType != "CHANNEL":
            me = self.participantRepository.get(conversation.id, actorId)
            if me is None or not me.isActive():
                raise PermissionDeniedError(action="message.list")
        page = self.messageRepository.listByConversation(
            tenantId,
            conversation.id,
            beforeId=asUuid(query.beforeId) if query.beforeId else None,
            limit=query.limit,
            threadRootId=asUuid(query.threadRootId) if query.threadRootId else None,
        )
        items = [
            messageDtoFromDomain(
                message,
                reactions=[
                    ReactionDto(userId=str(r.userId), reaction=r.reaction)
                    for r in self.reactionRepository.listForMessage(message.id)
                ],
                attachments=[
                    AttachmentDto(
                        id=str(a.id),
                        fileName=a.fileName,
                        mimeType=a.mimeType,
                        sizeBytes=a.sizeBytes,
                        documentRef=a.documentRef,
                    )
                    for a in self.attachmentRepository.listForMessage(message.id)
                ],
            )
            for message in page.items
        ]
        return MessagePageDto(
            items=items, totalCount=page.totalCount, hasNext=page.hasNext
        )


class SearchMessagesUseCase(CommunicationUseCase[SearchMessagesQuery, list[MessageDto]]):
    """§22 — search over the user's OWN conversations; the backend stays
    replaceable (port) — the domain never depends on a search engine."""

    requiredAction = ""

    def __init__(
        self,
        messageRepository: MessageRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.messageRepository = messageRepository

    def validateCommand(self, query: SearchMessagesQuery) -> None:
        if not query.query.strip():
            raise ValidationFailedError(
                "Search query is required.", fieldErrors={"query": "empty"}
            )

    def perform(self, query: SearchMessagesQuery) -> list[MessageDto]:
        actorId, tenantId = actorOf()
        hits = self.messageRepository.search(
            tenantId, actorId, query.query.strip(), limit=query.limit
        )
        return [messageDtoFromDomain(message) for message in hits]


class ListPinsUseCase(CommunicationUseCase[ListPinsQuery, list[PinDto]]):
    requiredAction = ""

    def __init__(
        self,
        conversationRepository: ConversationRepository,
        participantRepository: ParticipantRepository,
        pinRepository: PinRepository,
        **kernel: object,
    ) -> None:
        super().__init__(**kernel)
        self.conversationRepository = conversationRepository
        self.participantRepository = participantRepository
        self.pinRepository = pinRepository

    def perform(self, query: ListPinsQuery) -> list[PinDto]:
        actorId, tenantId = actorOf()
        conversation = self.conversationRepository.getById(
            asUuid(query.conversationId), tenantId
        )
        if conversation is None:
            raise EntityNotFoundError("Conversation", query.conversationId)
        if conversation.conversationType != "CHANNEL":
            me = self.participantRepository.get(conversation.id, actorId)
            if me is None or not me.isActive():
                raise PermissionDeniedError(action="message.list")
        return [
            PinDto(
                messageId=str(pin.messageId),
                conversationId=str(pin.conversationId),
                pinnedBy=str(pin.pinnedBy),
                pinnedAt=pin.pinnedAt.isoformat(),
            )
            for pin in self.pinRepository.listForConversation(conversation.id)
        ]
