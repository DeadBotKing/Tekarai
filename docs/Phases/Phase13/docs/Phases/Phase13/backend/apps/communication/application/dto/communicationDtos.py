"""Communication DTOs (Phase 08 §30)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConversationDto:
    id: str
    tenantId: str
    type: str
    name: str
    description: str = ""
    topic: str = ""
    visibility: str = ""
    isActive: bool = True
    archivedAt: str = ""
    createdAt: str = ""
    lastMessageAt: str = ""
    lastMessagePreview: str = ""
    unreadCount: int = 0


@dataclass(frozen=True)
class ParticipantDto:
    id: str
    conversationId: str
    userId: str
    role: str
    joinedAt: str = ""
    leftAt: str = ""
    isMuted: bool = False
    notificationLevel: str = "ALL"
    isActive: bool = True


@dataclass(frozen=True)
class AttachmentDto:
    id: str
    fileName: str
    mimeType: str
    sizeBytes: int
    documentRef: str = ""


@dataclass(frozen=True)
class ReactionDto:
    userId: str
    reaction: str


@dataclass(frozen=True)
class MessageDto:
    id: str
    conversationId: str
    senderId: str
    messageType: str
    body: str
    createdAt: str
    replyToId: str = ""
    clientRequestId: str = ""
    mentions: list[str] = field(default_factory=list)
    editedAt: str = ""
    deletedAt: str = ""
    deleted: bool = False
    attachments: list[AttachmentDto] = field(default_factory=list)
    reactions: list[ReactionDto] = field(default_factory=list)


@dataclass(frozen=True)
class MessagePageDto:
    items: list[MessageDto] = field(default_factory=list)
    totalCount: int = 0
    hasNext: bool = False

    def asMeta(self) -> dict[str, Any]:
        return {
            "pagination": {
                "totalCount": self.totalCount,
                "pageSize": len(self.items),
                "hasNext": self.hasNext,
            }
        }


@dataclass(frozen=True)
class PinDto:
    messageId: str
    conversationId: str
    pinnedBy: str
    pinnedAt: str = ""


@dataclass(frozen=True)
class MeetingDto:
    id: str
    conversationId: str
    organizerId: str
    title: str
    description: str = ""
    meetingStatus: str = "SCHEDULED"
    scheduledStart: str = ""
    scheduledEnd: str = ""
    actualStart: str = ""
    actualEnd: str = ""
    createdAt: str = ""
    participants: list[dict[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class CallDto:
    id: str
    mediaType: str
    callStatus: str
    initiatorId: str
    conversationId: str = ""
    meetingId: str = ""
    createdAt: str = ""
    startedAt: str = ""
    endedAt: str = ""


@dataclass(frozen=True)
class RecordingDto:
    id: str
    meetingId: str
    recordingStatus: str
    requestedBy: str = ""
    startedAt: str = ""
    stoppedAt: str = ""
    durationSeconds: int = 0
    storageRef: str = ""


@dataclass(frozen=True)
class LetterDto:
    id: str
    referenceNumber: str
    senderId: str
    recipientId: str
    subject: str
    body: str = ""
    recipientOrganization: str = ""
    recipientUnit: str = ""
    letterStatus: str = "DRAFT"
    createdAt: str = ""
    approvedBy: str = ""
    signedBy: str = ""
    dispatchedAt: str = ""
    receivedAt: str = ""


@dataclass(frozen=True)
class AiSummaryDto:
    meetingId: str
    summary: str
    actionItems: list[str] = field(default_factory=list)


def messageDtoFromDomain(
    message: Any,
    *,
    attachments: list[AttachmentDto] | None = None,
    reactions: list[ReactionDto] | None = None,
) -> MessageDto:
    return MessageDto(
        id=str(message.id),
        conversationId=str(message.conversationId),
        senderId=str(message.senderId),
        messageType=message.messageType,
        # §34 — deleted content is withheld from transport; the stored row
        # remains governed by retention policy.
        body="" if message.deletedAt else message.body,
        createdAt=message.createdAt.isoformat(),
        replyToId=str(message.replyToId) if message.replyToId else "",
        clientRequestId=message.clientRequestId,
        mentions=list(message.mentions),
        editedAt=message.editedAt.isoformat() if message.editedAt else "",
        deletedAt=message.deletedAt.isoformat() if message.deletedAt else "",
        deleted=message.deletedAt is not None,
        attachments=attachments or [],
        reactions=reactions or [],
    )
