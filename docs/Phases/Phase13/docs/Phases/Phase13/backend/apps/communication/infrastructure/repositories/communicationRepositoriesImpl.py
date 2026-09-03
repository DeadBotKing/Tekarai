"""Communication repository ORM implementations (Phase 08 §36)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from django.db.models import F, Q

from apps.communication.domain.entities.call import Call, CallParticipant
from apps.communication.domain.entities.conversation import Conversation
from apps.communication.domain.entities.meeting import Meeting, MeetingParticipant
from apps.communication.domain.entities.message import (
    Message,
    MessageAttachment,
    MessageReaction,
    MessageReadState,
    PinnedMessage,
)
from apps.communication.domain.entities.officialLetter import OfficialLetter
from apps.communication.domain.entities.participant import ConversationParticipant
from apps.communication.domain.entities.recording import Recording
from apps.communication.domain.repositories.communicationRepositories import (
    ConversationSummary,
    MessagePage,
)
from apps.communication.infrastructure.models import (
    CallModel,
    CallParticipantModel,
    ChannelMembershipModel,
    ChannelProfileModel,
    ConversationModel,
    ConversationParticipantModel,
    MeetingModel,
    MeetingParticipantModel,
    MessageAttachmentModel,
    MessageMentionModel,
    MessageModel,
    MessageReactionModel,
    MessageReadStateModel,
    OfficialLetterModel,
    OutboxModel,
    PinnedMessageModel,
    RecordingModel,
)

# ---------------------------------------------------------------------------
# conversations / channels / participants
# ---------------------------------------------------------------------------


class ConversationRepositoryDjango:
    def create(
        self,
        conversation: Conversation,
        *,
        code: str = "",
        topic: str = "",
        visibility: str = "",
    ) -> None:
        ConversationModel.objects.create(
            id=conversation.id,
            tenantId=conversation.tenantId,
            conversationType=conversation.conversationType,
            name=conversation.name,
            description=conversation.description,
            directKey=conversation.directKey,
            isActive=conversation.isActive,
            createdBy=conversation.createdBy,
        )
        if conversation.conversationType == "CHANNEL":
            ChannelProfileModel.objects.create(
                conversationId=conversation.id,
                tenantId=conversation.tenantId,
                code=code.lower(),
                topic=topic,
                visibility=visibility or "PUBLIC",
            )
            ChannelMembershipModel.objects.create(
                conversationId=conversation.id,
                tenantId=conversation.tenantId,
                userId=conversation.createdBy or conversation.id,
            )

    def update(self, conversation: Conversation) -> None:
        ConversationModel.objects.filter(id=conversation.id).update(
            name=conversation.name,
            description=conversation.description,
            isActive=conversation.isActive,
            archivedAt=conversation.archivedAt,
            updatedAt=datetime.now(tz=timezone.utc),
        )

    def updateChannelProfile(
        self,
        conversationId: uuid.UUID,
        *,
        topic: str | None,
        visibility: str | None,
        description: str | None,
        name: str | None,
    ) -> None:
        updates: dict[str, Any] = {}
        if topic is not None:
            updates["topic"] = topic
        if visibility is not None:
            updates["visibility"] = visibility
        if updates:
            ChannelProfileModel.objects.filter(conversationId=conversationId).update(
                **updates, updatedAt=datetime.now(tz=timezone.utc)
            )
        if description is not None or name is not None:
            self.update(
                Conversation(
                    id=conversationId,
                    tenantId=uuid.UUID(int=0),
                    conversationType="GROUP",
                    createdAt=datetime.now(tz=timezone.utc),
                    name=name or "",
                    description=description or "",
                )
            )

    def getById(
        self, conversationId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Conversation | None:
        queryset = ConversationModel.objects.filter(id=conversationId)
        if tenantId is not None:
            queryset = queryset.filter(tenantId=tenantId)  # §18 tenant scope
        model = queryset.first()
        return self.toDomain(model) if model else None

    def getByDirectKey(self, tenantId: uuid.UUID, directKey: str) -> Conversation | None:
        model = ConversationModel.objects.filter(
            tenantId=tenantId, directKey=directKey, conversationType="DIRECT"
        ).first()
        return self.toDomain(model) if model else None

    def channelCodeExists(self, tenantId: uuid.UUID, code: str) -> bool:
        return ChannelProfileModel.objects.filter(tenantId=tenantId, code=code).exists()

    def channelProfileOf(self, conversationId: uuid.UUID) -> tuple[str, str]:
        profile = ChannelProfileModel.objects.filter(
            conversationId=conversationId
        ).first()
        return (profile.topic, profile.visibility) if profile else ("", "")

    def listForUser(
        self, tenantId: uuid.UUID, userId: uuid.UUID, *, includeArchived: bool = False
    ) -> list[ConversationSummary]:
        ids = list(
            ConversationParticipantModel.objects.filter(
                tenantId=tenantId, userId=userId, leftAt__isnull=True
            ).values_list("conversationId", flat=True)
        )
        channelIds = list(
            ChannelProfileModel.objects.filter(
                tenantId=tenantId, visibility="PUBLIC"
            ).values_list("conversationId", flat=True)
        )
        allIds = list(dict.fromkeys([*ids, *channelIds]))
        if not allIds:
            return []
        queryset = ConversationModel.objects.filter(
            tenantId=tenantId, id__in=allIds
        ).order_by("-updatedAt")
        if not includeArchived:
            queryset = queryset.filter(archivedAt__isnull=True)
        summaries: list[ConversationSummary] = []
        for model in queryset:
            lastMessage = (
                MessageModel.objects.filter(
                    conversationId=model.id, deletedAt__isnull=True
                )
                .order_by("-createdAt")
                .first()
            )
            lastRead = (
                ConversationParticipantModel.objects.filter(
                    conversationId=model.id, userId=userId
                )
                .values_list("lastReadMessageId", flat=True)
                .first()
            )
            unread = MessageModel.objects.filter(
                conversationId=model.id, deletedAt__isnull=True
            )
            if lastRead:
                readCreatedAt = (
                    MessageModel.objects.filter(id=lastRead)
                    .values_list("createdAt", flat=True)
                    .first()
                )
                if readCreatedAt is not None:
                    unread = unread.filter(createdAt__gt=readCreatedAt)
            topic, visibility = ("", "")
            if model.conversationType == "CHANNEL":
                topic, visibility = self.channelProfileOf(model.id)
            summaries.append(
                ConversationSummary(
                    id=model.id,
                    tenantId=model.tenantId,
                    conversationType=model.conversationType,
                    name=model.name,
                    description=model.description,
                    directKey=model.directKey,
                    isActive=model.isActive,
                    archivedAt=model.archivedAt,
                    createdAt=model.createdAt,
                    lastMessageAt=lastMessage.createdAt if lastMessage else None,
                    lastMessagePreview=(lastMessage.body[:80] if lastMessage else ""),
                    unreadCount=unread.exclude(senderId=userId).count(),
                    topic=topic,
                    visibility=visibility,
                )
            )
        return summaries

    @staticmethod
    def toDomain(model: ConversationModel) -> Conversation:
        return Conversation(
            id=model.id,
            tenantId=model.tenantId,
            conversationType=model.conversationType,
            createdAt=model.createdAt,
            createdBy=model.createdBy,
            name=model.name,
            description=model.description,
            directKey=model.directKey,
            isActive=model.isActive,
            archivedAt=model.archivedAt,
            updatedAt=model.updatedAt,
        )


class ChannelProfileReader:
    """Channel profile adapter for use cases (§4 visibility/topic)."""

    def visibilityOf(self, conversationId: uuid.UUID) -> str:
        return self.visibilityOfOr(conversationId, "PUBLIC")

    def profileOf(self, conversationId: uuid.UUID) -> tuple[str, str]:
        profile = ChannelProfileModel.objects.filter(
            conversationId=conversationId
        ).first()
        return (profile.topic, profile.visibility) if profile else ("", "")

    def visibilityOfOr(self, conversationId: uuid.UUID, default: str) -> str:
        profile = ChannelProfileModel.objects.filter(
            conversationId=conversationId
        ).first()
        return profile.visibility if profile else default


class ParticipantRepositoryDjango:
    def add(self, participant: ConversationParticipant) -> None:
        ConversationParticipantModel.objects.create(
            id=participant.id,
            conversationId=participant.conversationId,
            tenantId=participant.tenantId,
            userId=participant.userId,
            role=participant.role,
            invitedBy=participant.invitedBy,
            isMuted=participant.isMuted,
            notificationLevel=participant.notificationLevel,
            lastReadMessageId=participant.lastReadMessageId,
        )
        if participant.role in ("MEMBER", "GUEST"):
            membership, created = ChannelMembershipModel.objects.get_or_create(
                conversationId=participant.conversationId,
                userId=participant.userId,
                leftAt__isnull=True,
                defaults={"tenantId": participant.tenantId},
            )
            del membership, created

    def update(self, participant: ConversationParticipant) -> None:
        ConversationParticipantModel.objects.filter(id=participant.id).update(
            role=participant.role,
            leftAt=participant.leftAt,
            isMuted=participant.isMuted,
            notificationLevel=participant.notificationLevel,
            lastReadMessageId=participant.lastReadMessageId,
            updatedAt=datetime.now(tz=timezone.utc),
        )

    def get(
        self, conversationId: uuid.UUID, userId: uuid.UUID
    ) -> ConversationParticipant | None:
        model = ConversationParticipantModel.objects.filter(
            conversationId=conversationId, userId=userId
        ).first()
        return self.toDomain(model) if model else None

    def listForConversation(
        self, conversationId: uuid.UUID
    ) -> list[ConversationParticipant]:
        models = ConversationParticipantModel.objects.filter(
            conversationId=conversationId
        ).order_by("joinedAt")
        return [self.toDomain(model) for model in models]

    def activeUserIdsOf(self, conversationId: uuid.UUID) -> list[uuid.UUID]:
        return list(
            ConversationParticipantModel.objects.filter(
                conversationId=conversationId, leftAt__isnull=True
            ).values_list("userId", flat=True)
        )

    def activeConversationIdsOf(self, userId: uuid.UUID) -> list[uuid.UUID]:
        return list(
            ConversationParticipantModel.objects.filter(
                userId=userId, leftAt__isnull=True
            ).values_list("conversationId", flat=True)
        )

    @staticmethod
    def toDomain(model: ConversationParticipantModel) -> ConversationParticipant:
        return ConversationParticipant(
            id=model.id,
            conversationId=model.conversationId,
            tenantId=model.tenantId,
            userId=model.userId,
            role=model.role,
            joinedAt=model.joinedAt,
            leftAt=model.leftAt,
            isMuted=model.isMuted,
            notificationLevel=model.notificationLevel,
            lastReadMessageId=model.lastReadMessageId,
        )


# ---------------------------------------------------------------------------
# messages
# ---------------------------------------------------------------------------


class MessageRepositoryDjango:
    def create(self, message: Message) -> None:
        MessageModel.objects.create(
            id=message.id,
            tenantId=message.tenantId,
            conversationId=message.conversationId,
            senderId=message.senderId,
            messageType=message.messageType,
            body=message.body,
            replyToId=message.replyToId,
            threadRootId=message.threadRootId,
            clientRequestId=message.clientRequestId,
            editedAt=message.editedAt,
            deletedAt=message.deletedAt,
        )
        rows = [
            MessageMentionModel(
                tenantId=message.tenantId,
                messageId=message.id,
                mentionedUserId=uuid.UUID(value),
            )
            for value in message.mentions
        ]
        if rows:
            MessageMentionModel.objects.bulk_create(rows)

    def update(self, message: Message) -> None:
        MessageModel.objects.filter(id=message.id).update(
            body=message.body,
            editedAt=message.editedAt,
            deletedAt=message.deletedAt,
            updatedAt=datetime.now(tz=timezone.utc),
        )

    def getById(
        self, messageId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Message | None:
        queryset = MessageModel.objects.filter(id=messageId)
        if tenantId is not None:
            queryset = queryset.filter(tenantId=tenantId)
        model = queryset.first()
        return self.toDomain(model) if model else None

    def findByIdempotencyKey(
        self,
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        senderId: uuid.UUID,
        clientRequestId: str,
    ) -> Message | None:
        model = MessageModel.objects.filter(
            tenantId=tenantId,
            conversationId=conversationId,
            senderId=senderId,
            clientRequestId=clientRequestId,
        ).first()
        return self.toDomain(model) if model else None

    def listByConversation(
        self,
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        *,
        beforeId: uuid.UUID | None = None,
        limit: int = 50,
        threadRootId: uuid.UUID | None = None,
    ) -> MessagePage:
        queryset = MessageModel.objects.filter(
            tenantId=tenantId, conversationId=conversationId
        )
        if threadRootId is not None:
            # §14 — group every reply under the same root (deep replies too).
            queryset = queryset.filter(threadRootId=threadRootId)
        if beforeId is not None:
            anchor = (
                MessageModel.objects.filter(id=beforeId)
                .values_list("createdAt", flat=True)
                .first()
            )
            if anchor is not None:
                queryset = queryset.filter(createdAt__lt=anchor)
        total = queryset.count()
        models = list(queryset.order_by("-createdAt")[: limit + 1])
        hasNext = len(models) > limit
        models = list(reversed(models[:limit]))
        return MessagePage(
            items=[self.toDomain(model) for model in models],
            totalCount=total,
            hasNext=hasNext,
        )

    def search(
        self, tenantId: uuid.UUID, userId: uuid.UUID, query: str, *, limit: int = 25
    ) -> list[Message]:
        """§22 — search restricted to the user's conversations."""
        conversationIds = list(
            ConversationParticipantModel.objects.filter(
                tenantId=tenantId, userId=userId, leftAt__isnull=True
            ).values_list("conversationId", flat=True)
        )
        if not conversationIds:
            return []
        models = (
            MessageModel.objects.filter(
                tenantId=tenantId,
                conversationId__in=conversationIds,
                deletedAt__isnull=True,
                body__icontains=query,
            )
            .order_by("-createdAt")[:limit]
        )
        return [self.toDomain(model) for model in models]

    def latestIdAtOrBefore(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID, messageId: uuid.UUID
    ) -> uuid.UUID | None:
        return messageId

    @staticmethod
    def toDomain(model: MessageModel) -> Message:
        mentions = tuple(
            str(value)
            for value in MessageMentionModel.objects.filter(messageId=model.id)
            .order_by("id")
            .values_list("mentionedUserId", flat=True)
        )
        return Message(
            id=model.id,
            tenantId=model.tenantId,
            conversationId=model.conversationId,
            senderId=model.senderId,
            messageType=model.messageType,
            createdAt=model.createdAt,
            body=model.body,
            replyToId=model.replyToId,
            threadRootId=model.threadRootId,
            clientRequestId=model.clientRequestId,
            mentions=mentions,
            editedAt=model.editedAt,
            deletedAt=model.deletedAt,
        )


class AttachmentRepositoryDjango:
    def add(self, attachment: MessageAttachment) -> None:
        MessageAttachmentModel.objects.create(
            id=attachment.id,
            tenantId=attachment.tenantId,
            messageId=attachment.messageId,
            fileName=attachment.fileName,
            mimeType=attachment.mimeType,
            sizeBytes=attachment.sizeBytes,
            documentRef=attachment.documentRef,
        )

    def listForMessage(self, messageId: uuid.UUID) -> list[MessageAttachment]:
        models = MessageAttachmentModel.objects.filter(messageId=messageId)
        return [
            MessageAttachment(
                id=model.id,
                tenantId=model.tenantId,
                messageId=model.messageId,
                fileName=model.fileName,
                mimeType=model.mimeType,
                sizeBytes=model.sizeBytes,
                createdAt=model.createdAt,
                documentRef=model.documentRef,
            )
            for model in models
        ]


class ReactionRepositoryDjango:
    def add(self, reaction: MessageReaction) -> None:
        MessageReactionModel.objects.create(
            id=reaction.id,
            tenantId=reaction.tenantId,
            messageId=reaction.messageId,
            userId=reaction.userId,
            reaction=reaction.reaction,
        )

    def remove(self, messageId: uuid.UUID, userId: uuid.UUID, reaction: str) -> bool:
        deleted, _ = MessageReactionModel.objects.filter(
            messageId=messageId, userId=userId, reaction=reaction
        ).delete()
        return deleted > 0

    def listForMessage(self, messageId: uuid.UUID) -> list[MessageReaction]:
        models = MessageReactionModel.objects.filter(messageId=messageId)
        return [
            MessageReaction(
                id=model.id,
                tenantId=model.tenantId,
                messageId=model.messageId,
                userId=model.userId,
                reaction=model.reaction,
                createdAt=model.createdAt,
            )
            for model in models
        ]

    def exists(self, messageId: uuid.UUID, userId: uuid.UUID, reaction: str) -> bool:
        return MessageReactionModel.objects.filter(
            messageId=messageId, userId=userId, reaction=reaction
        ).exists()


class ReadStateRepositoryDjango:
    """§32 — bulk statements; a per-message row is created lazily."""

    def markConversationRead(
        self,
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        userId: uuid.UUID,
        uptoMessageId: uuid.UUID,
        now: datetime,
    ) -> int:
        anchor = (
            MessageModel.objects.filter(id=uptoMessageId)
            .values_list("createdAt", flat=True)
            .first()
        )
        if anchor is None:
            return 0
        messageIds = list(
            MessageModel.objects.filter(
                tenantId=tenantId,
                conversationId=conversationId,
                deletedAt__isnull=True,
                createdAt__lte=anchor,
            )
            .exclude(senderId=userId)
            .values_list("id", flat=True)
        )
        existing = set(
            MessageReadStateModel.objects.filter(
                messageId__in=messageIds, userId=userId
            ).values_list("messageId", flat=True)
        )
        rows = [
            MessageReadStateModel(
                tenantId=tenantId,
                conversationId=conversationId,
                messageId=messageId,
                userId=userId,
                state="READ",
            )
            for messageId in messageIds
            if messageId not in existing
        ]
        if rows:
            MessageReadStateModel.objects.bulk_create(rows, ignore_conflicts=True)
        updated = MessageReadStateModel.objects.filter(
            messageId__in=messageIds, userId=userId
        ).exclude(state="READ").update(state="READ", updatedAt=now)
        return len(rows) + updated

    def markDelivered(
        self,
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        userIds: list[uuid.UUID],
        now: datetime,
    ) -> int:
        del tenantId, conversationId, userIds, now
        return 0  # delivery marks ride on the WS broadcast (§32); kept for the port

    def statesForMessage(self, messageId: uuid.UUID) -> list[MessageReadState]:
        models = MessageReadStateModel.objects.filter(messageId=messageId)
        return [
            MessageReadState(
                id=model.id,
                tenantId=model.tenantId,
                conversationId=model.conversationId,
                messageId=model.messageId,
                userId=model.userId,
                state=model.state,
                updatedAt=model.updatedAt,
            )
            for model in models
        ]

    def unreadCount(
        self,
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        userId: uuid.UUID,
        lastReadMessageId: uuid.UUID | None,
    ) -> int:
        queryset = MessageModel.objects.filter(
            tenantId=tenantId, conversationId=conversationId, deletedAt__isnull=True
        ).exclude(senderId=userId)
        if lastReadMessageId is not None:
            anchor = (
                MessageModel.objects.filter(id=lastReadMessageId)
                .values_list("createdAt", flat=True)
                .first()
            )
            if anchor is not None:
                queryset = queryset.filter(createdAt__gt=anchor)
        return queryset.count()


class PinRepositoryDjango:
    def pin(self, pin: PinnedMessage) -> None:
        PinnedMessageModel.objects.create(
            id=pin.id,
            tenantId=pin.tenantId,
            conversationId=pin.conversationId,
            messageId=pin.messageId,
            pinnedBy=pin.pinnedBy,
        )

    def unpin(self, conversationId: uuid.UUID, messageId: uuid.UUID) -> bool:
        deleted, _ = PinnedMessageModel.objects.filter(
            conversationId=conversationId, messageId=messageId
        ).delete()
        return deleted > 0

    def listForConversation(self, conversationId: uuid.UUID) -> list[PinnedMessage]:
        models = PinnedMessageModel.objects.filter(
            conversationId=conversationId
        ).order_by("-pinnedAt")
        return [
            PinnedMessage(
                id=model.id,
                tenantId=model.tenantId,
                conversationId=model.conversationId,
                messageId=model.messageId,
                pinnedBy=model.pinnedBy,
                pinnedAt=model.pinnedAt,
            )
            for model in models
        ]

    def isPinned(self, conversationId: uuid.UUID, messageId: uuid.UUID) -> bool:
        return PinnedMessageModel.objects.filter(
            conversationId=conversationId, messageId=messageId
        ).exists()


# ---------------------------------------------------------------------------
# meetings
# ---------------------------------------------------------------------------


class MeetingRepositoryDjango:
    def create(self, meeting: Meeting) -> None:
        MeetingModel.objects.create(
            id=meeting.id,
            tenantId=meeting.tenantId,
            conversationId=meeting.conversationId,
            organizerId=meeting.organizerId,
            title=meeting.title,
            description=meeting.description,
            scheduledStart=meeting.scheduledStart,
            scheduledEnd=meeting.scheduledEnd,
            meetingStatus=meeting.meetingStatus,
            clientRequestId=meeting.clientRequestId,
        )

    def update(self, meeting: Meeting) -> None:
        MeetingModel.objects.filter(id=meeting.id).update(
            title=meeting.title,
            description=meeting.description,
            meetingStatus=meeting.meetingStatus,
            actualStart=meeting.actualStart,
            actualEnd=meeting.actualEnd,
            scheduledStart=meeting.scheduledStart,
            scheduledEnd=meeting.scheduledEnd,
            updatedAt=datetime.now(tz=timezone.utc),
        )

    def getById(
        self, meetingId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Meeting | None:
        queryset = MeetingModel.objects.filter(id=meetingId)
        if tenantId is not None:
            queryset = queryset.filter(tenantId=tenantId)
        model = queryset.first()
        return self.toDomain(model) if model else None

    def listByConversation(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID
    ) -> list[Meeting]:
        models = MeetingModel.objects.filter(
            tenantId=tenantId, conversationId=conversationId
        ).order_by("-createdAt")
        return [self.toDomain(model) for model in models]

    def findActiveForOrganizer(
        self, tenantId: uuid.UUID, organizerId: uuid.UUID
    ) -> list[Meeting]:
        models = MeetingModel.objects.filter(
            tenantId=tenantId,
            organizerId=organizerId,
            meetingStatus__in=("SCHEDULED", "WAITING", "LIVE"),
        )
        return [self.toDomain(model) for model in models]

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, organizerId: uuid.UUID, clientRequestId: str
    ) -> Meeting | None:
        model = MeetingModel.objects.filter(
            tenantId=tenantId,
            organizerId=organizerId,
            clientRequestId=clientRequestId,
        ).first()
        return self.toDomain(model) if model else None

    @staticmethod
    def toDomain(model: MeetingModel) -> Meeting:
        return Meeting(
            id=model.id,
            tenantId=model.tenantId,
            conversationId=model.conversationId,
            organizerId=model.organizerId,
            title=model.title,
            description=model.description,
            createdAt=model.createdAt,
            scheduledStart=model.scheduledStart,
            scheduledEnd=model.scheduledEnd,
            actualStart=model.actualStart,
            actualEnd=model.actualEnd,
            meetingStatus=model.meetingStatus,
            clientRequestId=model.clientRequestId,
        )


class MeetingParticipantRepositoryDjango:
    def add(self, participant: MeetingParticipant) -> None:
        MeetingParticipantModel.objects.create(
            id=participant.id,
            tenantId=participant.tenantId,
            meetingId=participant.meetingId,
            userId=participant.userId,
            status=participant.status,
            role=participant.role,
            attendanceDuration=participant.attendanceDuration,
        )

    def update(self, participant: MeetingParticipant) -> None:
        MeetingParticipantModel.objects.filter(id=participant.id).update(
            status=participant.status,
            role=participant.role,
            attendanceDuration=participant.attendanceDuration,
            respondedAt=participant.respondedAt,
            joinedAt=participant.joinedAt,
            leftAt=participant.leftAt,
            updatedAt=datetime.now(tz=timezone.utc),
        )

    def get(
        self, meetingId: uuid.UUID, userId: uuid.UUID
    ) -> MeetingParticipant | None:
        model = MeetingParticipantModel.objects.filter(
            meetingId=meetingId, userId=userId
        ).first()
        return self.toDomain(model) if model else None

    def listForMeeting(self, meetingId: uuid.UUID) -> list[MeetingParticipant]:
        models = MeetingParticipantModel.objects.filter(meetingId=meetingId)
        return [self.toDomain(model) for model in models]

    def joinedUserIds(self, meetingId: uuid.UUID) -> list[uuid.UUID]:
        return list(
            MeetingParticipantModel.objects.filter(
                meetingId=meetingId, status="JOINED"
            ).values_list("userId", flat=True)
        )

    @staticmethod
    def toDomain(model: MeetingParticipantModel) -> MeetingParticipant:
        return MeetingParticipant(
            id=model.id,
            tenantId=model.tenantId,
            meetingId=model.meetingId,
            userId=model.userId,
            status=model.status,
            createdAt=model.createdAt,
            role=model.role or "PARTICIPANT",
            attendanceDuration=model.attendanceDuration or 0,
            respondedAt=model.respondedAt,
            joinedAt=model.joinedAt,
            leftAt=model.leftAt,
        )


# ---------------------------------------------------------------------------
# calls
# ---------------------------------------------------------------------------


class CallRepositoryDjango:
    def create(self, call: Call) -> None:
        CallModel.objects.create(
            id=call.id,
            tenantId=call.tenantId,
            initiatorId=call.initiatorId,
            conversationId=call.conversationId,
            meetingId=call.meetingId,
            mediaType=call.mediaType,
            callStatus=call.callStatus,
            clientRequestId=call.clientRequestId,
            mediaSessionRef=getattr(call, "mediaSessionRef", ""),
        )

    def update(self, call: Call) -> None:
        CallModel.objects.filter(id=call.id).update(
            callStatus=call.callStatus,
            startedAt=call.startedAt,
            endedAt=call.endedAt,
            mediaSessionRef=getattr(call, "mediaSessionRef", ""),
            updatedAt=datetime.now(tz=timezone.utc),
        )

    def getById(
        self, callId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Call | None:
        queryset = CallModel.objects.filter(id=callId)
        if tenantId is not None:
            queryset = queryset.filter(tenantId=tenantId)
        model = queryset.first()
        return self.toDomain(model) if model else None

    def findActiveInConversation(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID
    ) -> Call | None:
        model = CallModel.objects.filter(
            tenantId=tenantId,
            conversationId=conversationId,
            callStatus__in=("RINGING", "ACTIVE"),
        ).first()
        return self.toDomain(model) if model else None

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, initiatorId: uuid.UUID, clientRequestId: str
    ) -> Call | None:
        model = CallModel.objects.filter(
            tenantId=tenantId,
            initiatorId=initiatorId,
            clientRequestId=clientRequestId,
        ).first()
        return self.toDomain(model) if model else None

    @staticmethod
    def toDomain(model: CallModel) -> Call:
        call = Call(
            id=model.id,
            tenantId=model.tenantId,
            initiatorId=model.initiatorId,
            mediaType=model.mediaType,
            createdAt=model.createdAt,
            conversationId=model.conversationId,
            meetingId=model.meetingId,
            callStatus=model.callStatus,
            startedAt=model.startedAt,
            endedAt=model.endedAt,
            clientRequestId=model.clientRequestId,
        )
        call.mediaSessionRef = model.mediaSessionRef
        return call


class CallParticipantRepositoryDjango:
    def add(self, participant: CallParticipant) -> None:
        CallParticipantModel.objects.create(
            id=participant.id,
            tenantId=participant.tenantId,
            callId=participant.callId,
            userId=participant.userId,
            mediaState=participant.mediaState,
        )

    def update(self, participant: CallParticipant) -> None:
        CallParticipantModel.objects.filter(id=participant.id).update(
            leftAt=participant.leftAt, mediaState=participant.mediaState
        )

    def get(self, callId: uuid.UUID, userId: uuid.UUID) -> CallParticipant | None:
        model = CallParticipantModel.objects.filter(
            callId=callId, userId=userId
        ).first()
        return self.toDomain(model) if model else None

    def listForCall(self, callId: uuid.UUID) -> list[CallParticipant]:
        models = CallParticipantModel.objects.filter(callId=callId)
        return [self.toDomain(model) for model in models]

    @staticmethod
    def toDomain(model: CallParticipantModel) -> CallParticipant:
        return CallParticipant(
            id=model.id,
            tenantId=model.tenantId,
            callId=model.callId,
            userId=model.userId,
            joinedAt=model.joinedAt,
            leftAt=model.leftAt,
            mediaState=model.mediaState,
        )


# ---------------------------------------------------------------------------
# recordings
# ---------------------------------------------------------------------------


class RecordingRepositoryDjango:
    def create(self, recording: Recording) -> None:
        RecordingModel.objects.create(
            id=recording.id,
            tenantId=recording.tenantId,
            meetingId=recording.meetingId,
            requestedBy=recording.requestedBy,
            recordingStatus=recording.recordingStatus,
            startedAt=recording.startedAt,
            stoppedAt=recording.stoppedAt,
        )

    def update(self, recording: Recording) -> None:
        RecordingModel.objects.filter(id=recording.id).update(
            recordingStatus=recording.recordingStatus,
            startedAt=recording.startedAt,
            stoppedAt=recording.stoppedAt,
            storageRef=recording.storageRef,
            durationSeconds=recording.durationSeconds,
            failureReason=recording.failureReason,
            updatedAt=datetime.now(tz=timezone.utc),
        )

    def getById(
        self, recordingId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Recording | None:
        queryset = RecordingModel.objects.filter(id=recordingId)
        if tenantId is not None:
            queryset = queryset.filter(tenantId=tenantId)
        model = queryset.first()
        return self.toDomain(model) if model else None

    def findActiveForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> Recording | None:
        model = RecordingModel.objects.filter(
            tenantId=tenantId,
            meetingId=meetingId,
            recordingStatus__in=("REQUESTED", "STARTED", "PROCESSING"),
        ).first()
        return self.toDomain(model) if model else None

    def listForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> list[Recording]:
        models = RecordingModel.objects.filter(
            tenantId=tenantId, meetingId=meetingId
        ).order_by("-createdAt")
        return [self.toDomain(model) for model in models]

    @staticmethod
    def toDomain(model: RecordingModel) -> Recording:
        return Recording(
            id=model.id,
            tenantId=model.tenantId,
            meetingId=model.meetingId,
            requestedBy=model.requestedBy,
            createdAt=model.createdAt,
            recordingStatus=model.recordingStatus,
            startedAt=model.startedAt,
            stoppedAt=model.stoppedAt,
            storageRef=model.storageRef,
            durationSeconds=model.durationSeconds,
            failureReason=model.failureReason,
        )


# ---------------------------------------------------------------------------
# letters
# ---------------------------------------------------------------------------


class LetterRepositoryDjango:
    def create(self, letter: OfficialLetter) -> None:
        OfficialLetterModel.objects.create(
            id=letter.id,
            tenantId=letter.tenantId,
            referenceNumber=letter.referenceNumber,
            senderId=letter.senderId,
            recipientId=letter.recipientId,
            subject=letter.subject,
            body=letter.body,
            recipientOrganization=letter.recipientOrganization,
            recipientUnit=letter.recipientUnit,
            letterStatus=letter.letterStatus,
        )

    def update(self, letter: OfficialLetter) -> None:
        OfficialLetterModel.objects.filter(id=letter.id).update(
            letterStatus=letter.letterStatus,
            body=letter.body,
            subject=letter.subject,
            approvedBy=letter.approvedBy,
            signedBy=letter.signedBy,
            dispatchedAt=letter.dispatchedAt,
            receivedAt=letter.receivedAt,
            updatedAt=datetime.now(tz=timezone.utc),
        )

    def getById(
        self, letterId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> OfficialLetter | None:
        queryset = OfficialLetterModel.objects.filter(id=letterId)
        if tenantId is not None:
            queryset = queryset.filter(tenantId=tenantId)
        model = queryset.first()
        return self.toDomain(model) if model else None

    def getByReference(
        self, tenantId: uuid.UUID, referenceNumber: str
    ) -> OfficialLetter | None:
        model = OfficialLetterModel.objects.filter(
            tenantId=tenantId, referenceNumber=referenceNumber
        ).first()
        return self.toDomain(model) if model else None

    def nextReferenceNumber(self, tenantId: uuid.UUID) -> str:
        """Sequential per-tenant reference: YYYY-NNNNNN (§16)."""
        year = datetime.now(tz=timezone.utc).year
        last = (
            OfficialLetterModel.objects.filter(
                tenantId=tenantId, referenceNumber__startswith=f"{year}-"
            )
            .order_by("-referenceNumber")
            .values_list("referenceNumber", flat=True)
            .first()
        )
        sequence = int(last.split("-")[1]) + 1 if last else 1
        return f"{year}-{sequence:06d}"

    def list(
        self, tenantId: uuid.UUID, *, status: str = "", limit: int = 50
    ) -> list[OfficialLetter]:
        queryset = OfficialLetterModel.objects.filter(tenantId=tenantId)
        if status:
            queryset = queryset.filter(letterStatus=status)
        models = queryset.order_by("-createdAt")[:limit]
        return [self.toDomain(model) for model in models]

    @staticmethod
    def toDomain(model: OfficialLetterModel) -> OfficialLetter:
        return OfficialLetter(
            id=model.id,
            tenantId=model.tenantId,
            referenceNumber=model.referenceNumber,
            senderId=model.senderId,
            recipientId=model.recipientId,
            subject=model.subject,
            createdAt=model.createdAt,
            body=model.body,
            recipientOrganization=model.recipientOrganization,
            recipientUnit=model.recipientUnit,
            letterStatus=model.letterStatus,
            approvedBy=model.approvedBy,
            signedBy=model.signedBy,
            dispatchedAt=model.dispatchedAt,
            receivedAt=model.receivedAt,
        )


# ---------------------------------------------------------------------------
# outbox (§29)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OutboxRow:
    id: uuid.UUID
    tenantId: uuid.UUID
    eventType: str
    payload: dict
    occurredAt: datetime


class OutboxRepositoryDjango:
    def enqueue(
        self,
        *,
        tenantId: uuid.UUID,
        eventType: str,
        payload: dict,
        occurredAt: datetime,
    ) -> uuid.UUID:
        row = OutboxModel.objects.create(
            tenantId=tenantId,
            eventType=eventType,
            payload=payload,
            occurredAt=occurredAt,
        )
        return row.id

    def pending(self, *, limit: int = 100) -> list[OutboxRow]:
        rows = (
            OutboxModel.objects.filter(publishedAt__isnull=True)
            .order_by("occurredAt")[:limit]
        )
        return [
            OutboxRow(
                id=row.id,
                tenantId=row.tenantId,
                eventType=row.eventType,
                payload=row.payload,
                occurredAt=row.occurredAt,
            )
            for row in rows
        ]

    def markPublished(self, outboxId: uuid.UUID, now: datetime) -> None:
        OutboxModel.objects.filter(id=outboxId).update(
            publishedAt=now, attempts=F("attempts") + 1
        )
