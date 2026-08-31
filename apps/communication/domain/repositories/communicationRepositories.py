"""Communication repository contracts + real-time/AI/SFU ports (§36).

Everything the application layer may depend on; infrastructure implements.
The domain stays free of Django ORM, Redis, Channels and WebRTC (§37).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

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


# ---------------------------------------------------------------------------
# read models (no ORM objects cross the border)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MessagePage:
    items: list[Message] = field(default_factory=list)
    totalCount: int = 0
    hasNext: bool = False


@dataclass(frozen=True)
class ConversationSummary:
    id: uuid.UUID
    tenantId: uuid.UUID
    conversationType: str
    name: str
    description: str
    directKey: str
    isActive: bool
    archivedAt: datetime | None
    createdAt: datetime
    lastMessageAt: datetime | None = None
    lastMessagePreview: str = ""
    unreadCount: int = 0
    topic: str = ""
    visibility: str = ""


# ---------------------------------------------------------------------------
# conversations / participants (§3.1–§3.2)
# ---------------------------------------------------------------------------


@runtime_checkable
class ConversationRepository(Protocol):
    def create(self, conversation: Conversation, *, code: str = "",
               topic: str = "", visibility: str = "") -> None: ...

    def update(self, conversation: Conversation) -> None: ...

    def updateChannelProfile(
        self, conversationId: uuid.UUID, *, topic: str | None,
        visibility: str | None, description: str | None, name: str | None,
    ) -> None: ...

    def getById(
        self, conversationId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Conversation | None: ...

    def getByDirectKey(self, tenantId: uuid.UUID, directKey: str) -> Conversation | None: ...

    def channelCodeExists(self, tenantId: uuid.UUID, code: str) -> bool: ...

    def listForUser(
        self, tenantId: uuid.UUID, userId: uuid.UUID, *, includeArchived: bool = False
    ) -> list[ConversationSummary]: ...


@runtime_checkable
class ParticipantRepository(Protocol):
    def add(self, participant: ConversationParticipant) -> None: ...

    def update(self, participant: ConversationParticipant) -> None: ...

    def get(
        self, conversationId: uuid.UUID, userId: uuid.UUID
    ) -> ConversationParticipant | None: ...

    def listForConversation(self, conversationId: uuid.UUID) -> list[ConversationParticipant]: ...

    def activeUserIdsOf(self, conversationId: uuid.UUID) -> list[uuid.UUID]: ...

    def activeConversationIdsOf(self, userId: uuid.UUID) -> list[uuid.UUID]: ...


# ---------------------------------------------------------------------------
# messages / reactions / read states / pins (§3.3–§3.8, §32)
# ---------------------------------------------------------------------------


@runtime_checkable
class MessageRepository(Protocol):
    def create(self, message: Message) -> None: ...

    def update(self, message: Message) -> None: ...

    def getById(
        self, messageId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Message | None: ...

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID,
        senderId: uuid.UUID, clientRequestId: str,
    ) -> Message | None: ...

    def listByConversation(
        self,
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        *,
        beforeId: uuid.UUID | None = None,
        limit: int = 50,
        threadRootId: uuid.UUID | None = None,
    ) -> MessagePage: ...

    def search(
        self, tenantId: uuid.UUID, userId: uuid.UUID, query: str, *, limit: int = 25
    ) -> list[Message]: ...

    def latestIdAtOrBefore(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID, messageId: uuid.UUID
    ) -> uuid.UUID | None: ...


@runtime_checkable
class AttachmentRepository(Protocol):
    def add(self, attachment: MessageAttachment) -> None: ...

    def listForMessage(self, messageId: uuid.UUID) -> list[MessageAttachment]: ...


@runtime_checkable
class ReactionRepository(Protocol):
    def add(self, reaction: MessageReaction) -> None: ...

    def remove(self, messageId: uuid.UUID, userId: uuid.UUID, reaction: str) -> bool: ...

    def listForMessage(self, messageId: uuid.UUID) -> list[MessageReaction]: ...

    def exists(self, messageId: uuid.UUID, userId: uuid.UUID, reaction: str) -> bool: ...


@runtime_checkable
class ReadStateRepository(Protocol):
    """§32 — bulk updates to avoid excessive writes."""

    def markConversationRead(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID,
        userId: uuid.UUID, uptoMessageId: uuid.UUID, now: datetime,
    ) -> int: ...

    def markDelivered(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID,
        userIds: list[uuid.UUID], now: datetime,
    ) -> int: ...

    def statesForMessage(
        self, messageId: uuid.UUID
    ) -> list[MessageReadState]: ...

    def unreadCount(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID, userId: uuid.UUID,
        lastReadMessageId: uuid.UUID | None,
    ) -> int: ...


@runtime_checkable
class PinRepository(Protocol):
    def pin(self, pin: PinnedMessage) -> None: ...

    def unpin(self, conversationId: uuid.UUID, messageId: uuid.UUID) -> bool: ...

    def listForConversation(self, conversationId: uuid.UUID) -> list[PinnedMessage]: ...

    def isPinned(self, conversationId: uuid.UUID, messageId: uuid.UUID) -> bool: ...


# ---------------------------------------------------------------------------
# meetings / calls / recordings (§10, §13, §15)
# ---------------------------------------------------------------------------


@runtime_checkable
class MeetingRepository(Protocol):
    def create(self, meeting: Meeting) -> None: ...

    def update(self, meeting: Meeting) -> None: ...

    def getById(
        self, meetingId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Meeting | None: ...

    def listByConversation(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID
    ) -> list[Meeting]: ...

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, organizerId: uuid.UUID, clientRequestId: str
    ) -> Meeting | None: ...

    def findActiveForOrganizer(
        self, tenantId: uuid.UUID, organizerId: uuid.UUID
    ) -> list[Meeting]: ...


@runtime_checkable
class MeetingParticipantRepository(Protocol):
    def add(self, participant: MeetingParticipant) -> None: ...

    def update(self, participant: MeetingParticipant) -> None: ...

    def get(
        self, meetingId: uuid.UUID, userId: uuid.UUID
    ) -> MeetingParticipant | None: ...

    def listForMeeting(self, meetingId: uuid.UUID) -> list[MeetingParticipant]: ...

    def joinedUserIds(self, meetingId: uuid.UUID) -> list[uuid.UUID]: ...


@runtime_checkable
class CallRepository(Protocol):
    def create(self, call: Call) -> None: ...

    def update(self, call: Call) -> None: ...

    def getById(
        self, callId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Call | None: ...

    def findActiveInConversation(
        self, tenantId: uuid.UUID, conversationId: uuid.UUID
    ) -> Call | None: ...

    def findByIdempotencyKey(
        self, tenantId: uuid.UUID, initiatorId: uuid.UUID, clientRequestId: str
    ) -> Call | None: ...


@runtime_checkable
class CallParticipantRepository(Protocol):
    def add(self, participant: CallParticipant) -> None: ...

    def update(self, participant: CallParticipant) -> None: ...

    def get(self, callId: uuid.UUID, userId: uuid.UUID) -> CallParticipant | None: ...

    def listForCall(self, callId: uuid.UUID) -> list[CallParticipant]: ...


@runtime_checkable
class RecordingRepository(Protocol):
    def create(self, recording: Recording) -> None: ...

    def update(self, recording: Recording) -> None: ...

    def getById(
        self, recordingId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> Recording | None: ...

    def findActiveForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> Recording | None: ...

    def listForMeeting(self, tenantId: uuid.UUID, meetingId: uuid.UUID) -> list[Recording]: ...


# ---------------------------------------------------------------------------
# official letters (§16)
# ---------------------------------------------------------------------------


@runtime_checkable
class LetterRepository(Protocol):
    def create(self, letter: OfficialLetter) -> None: ...

    def update(self, letter: OfficialLetter) -> None: ...

    def getById(
        self, letterId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> OfficialLetter | None: ...

    def getByReference(self, tenantId: uuid.UUID, referenceNumber: str) -> OfficialLetter | None: ...

    def nextReferenceNumber(self, tenantId: uuid.UUID) -> str: ...

    def list(
        self, tenantId: uuid.UUID, *, status: str = "", limit: int = 50
    ) -> list[OfficialLetter]: ...


# ---------------------------------------------------------------------------
# presence (§7) — ephemeral store, TTL semantics, NOT SQL
# ---------------------------------------------------------------------------


@runtime_checkable
class PresenceRepository(Protocol):
    def set(
        self, tenantId: uuid.UUID, userId: uuid.UUID,
        status: str, ttlSeconds: int, now: datetime,
    ) -> None: ...

    def get(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str | None: ...

    def getMany(
        self, tenantId: uuid.UUID, userIds: list[uuid.UUID]
    ) -> dict[str, str]: ...


# ---------------------------------------------------------------------------
# outbox (§29)
# ---------------------------------------------------------------------------


@runtime_checkable
class OutboxRepository(Protocol):
    def enqueue(
        self, *, tenantId: uuid.UUID, eventType: str, payload: dict[str, Any],
        occurredAt: datetime,
    ) -> uuid.UUID: ...

    def pending(self, *, limit: int = 100) -> list[Any]: ...

    def markPublished(self, outboxId: uuid.UUID, now: datetime) -> None: ...


# ---------------------------------------------------------------------------
# real-time broadcasting (§8) — implemented over the channel layer
# ---------------------------------------------------------------------------


@runtime_checkable
class RealtimeBroadcaster(Protocol):
    def toConversation(self, conversationId: uuid.UUID, event: dict[str, Any]) -> None: ...

    def toUser(self, userId: uuid.UUID, event: dict[str, Any]) -> None: ...

    def toMeeting(self, meetingId: uuid.UUID, event: dict[str, Any]) -> None: ...

    def toCall(self, callId: uuid.UUID, event: dict[str, Any]) -> None: ...


# ---------------------------------------------------------------------------
# media routing / SFU (§12) — vendor-neutral port, adapter may be a no-op
# ---------------------------------------------------------------------------


@runtime_checkable
class MediaRouter(Protocol):
    def openSession(self, callId: str, mediaType: str) -> str: ...

    def joinSession(self, sessionId: str, userId: str) -> dict[str, Any]: ...

    def leaveSession(self, sessionId: str, userId: str) -> None: ...


# ---------------------------------------------------------------------------
# AI (§21) — provider-neutral; AI never mutates domain state directly
# ---------------------------------------------------------------------------


@runtime_checkable
class MeetingAiAssistant(Protocol):
    def summarize(self, transcript: list[str]) -> str: ...

    def extractActionItems(self, transcript: list[str]) -> list[str]: ...
