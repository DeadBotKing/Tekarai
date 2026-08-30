"""Message aggregate + attachment/reaction/read-state/mention/pin records
(Phase 08 §3.3–§3.8, §23, §24, §33, §34).

- ``clientRequestId`` gives offline clients deterministic retries — the same
  request can never materialize twice (§23/§24).
- Editing records ``editedAt`` and is ruled by the edit policy (§33);
  deletion is ALWAYS soft (§34).
- Attachments carry metadata ONLY and reference the future Documents
  subsystem — no storage architecture duplicated here (§3.4).
- Threading: a reply references its thread ROOT (§3.8); the conversation
  must match (domain rule).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.communication.domain.valueObjects.communicationTypes import (
    MESSAGE_TEXT,
    MESSAGE_TYPES,
    READ_DELIVERED,
    READ_READ,
    READ_SENT,
    READ_STATE_RANK,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId

BODY_MAX_LENGTH = 8000


class Message(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        senderId: uuid.UUID,
        messageType: str,
        createdAt: datetime,
        *,
        body: str = "",
        replyToId: uuid.UUID | None = None,
        clientRequestId: str = "",
        mentions: tuple[str, ...] = (),
        editedAt: datetime | None = None,
        deletedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        if messageType not in MESSAGE_TYPES:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unknown message type.", fieldErrors={"messageType": messageType}
            )
        self.tenantId = tenantId
        self.conversationId = conversationId
        self.senderId = senderId
        self.messageType = messageType
        self.createdAt = createdAt
        self.body = body
        self.replyToId = replyToId
        self.clientRequestId = clientRequestId
        self.mentions = tuple(mentions)
        self.editedAt = editedAt
        self.deletedAt = deletedAt

    # -- factory ----------------------------------------------------------------

    @staticmethod
    def send(
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        senderId: uuid.UUID,
        body: str,
        now: datetime,
        *,
        messageType: str = MESSAGE_TEXT,
        replyToId: uuid.UUID | None = None,
        clientRequestId: str = "",
        mentions: tuple[str, ...] = (),
    ) -> Message:
        if not body.strip() and messageType == MESSAGE_TEXT:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Message body is required.", fieldErrors={"body": "empty"}
            )
        if len(body) > BODY_MAX_LENGTH:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Message body is too long.",
                fieldErrors={"body": f"max {BODY_MAX_LENGTH}"},
            )
        message = Message(
            id=newId(),
            tenantId=tenantId,
            conversationId=conversationId,
            senderId=senderId,
            messageType=messageType,
            createdAt=now,
            body=body,
            replyToId=replyToId,
            clientRequestId=clientRequestId,
            mentions=mentions,
        )
        message.recordEvent(
            DomainEvent(
                name="messageCreated",
                occurredAt=now,
                tenantId=tenantId,
                actorId=senderId,
                payload={
                    "conversationId": str(conversationId),
                    "messageType": messageType,
                    "replyToId": str(replyToId) if replyToId else "",
                    "mentioned": len(mentions),
                },
            )
        )
        return message

    # -- behaviour (§33/§34) ----------------------------------------------------

    def edit(self, newBody: str, now: datetime) -> None:
        if self.deletedAt is not None:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Deleted messages cannot be edited.")
        if not newBody.strip():
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Message body is required.", fieldErrors={"body": "empty"}
            )
        if len(newBody) > BODY_MAX_LENGTH:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Message body is too long.",
                fieldErrors={"body": f"max {BODY_MAX_LENGTH}"},
            )
        self.body = newBody
        self.editedAt = now
        self.recordEvent(
            DomainEvent(
                name="messageEdited",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=self.senderId,
                payload={"messageId": str(self.id)},
            )
        )

    def delete(self, now: datetime) -> None:
        """§34 — soft delete: tombstone + audit; the row (and body) stays
        available to retention/legal policy. Physical purge is a separate,
        governed operation."""
        if self.deletedAt is not None:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Message is already deleted.")
        self.deletedAt = now
        self.recordEvent(
            DomainEvent(
                name="messageDeleted",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"messageId": str(self.id)},
            )
        )

    def belongsToConversation(self, conversationId: uuid.UUID) -> bool:
        return self.conversationId == conversationId

    def isDeleted(self) -> bool:
        return self.deletedAt is not None

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "conversationId": str(self.conversationId),
            "senderId": str(self.senderId),
            "messageType": self.messageType,
            "body": self.body,
            "replyToId": str(self.replyToId) if self.replyToId else "",
            "deleted": self.isDeleted(),
            "edited": self.editedAt is not None,
        }


class MessageAttachment(AggregateRoot):
    """§3.4 — metadata reference into the (future) Documents subsystem."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        messageId: uuid.UUID,
        fileName: str,
        mimeType: str,
        sizeBytes: int,
        createdAt: datetime,
        *,
        documentRef: str = "",
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.messageId = messageId
        self.fileName = fileName
        self.mimeType = mimeType
        self.sizeBytes = sizeBytes
        self.createdAt = createdAt
        self.documentRef = documentRef

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "fileName": self.fileName,
            "mimeType": self.mimeType,
            "sizeBytes": self.sizeBytes,
            "documentRef": self.documentRef,
        }


class MessageReaction(AggregateRoot):
    """§3.5 — (message, user, reaction) is unique; toggling removes."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        messageId: uuid.UUID,
        userId: uuid.UUID,
        reaction: str,
        createdAt: datetime,
    ) -> None:
        super().__init__(id)
        if not reaction.strip() or len(reaction) > 16:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Invalid reaction.", fieldErrors={"reaction": reaction}
            )
        self.tenantId = tenantId
        self.messageId = messageId
        self.userId = userId
        self.reaction = reaction.strip()
        self.createdAt = createdAt

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "messageId": str(self.messageId),
            "userId": str(self.userId),
            "reaction": self.reaction,
        }


class MessageReadState(AggregateRoot):
    """§3.6/§32 — per (message, user) delivery/read state, monotonic."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        messageId: uuid.UUID,
        userId: uuid.UUID,
        state: str,
        updatedAt: datetime,
    ) -> None:
        super().__init__(id)
        if state not in READ_STATE_RANK:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unknown read state.", fieldErrors={"state": state}
            )
        self.tenantId = tenantId
        self.conversationId = conversationId
        self.messageId = messageId
        self.userId = userId
        self.state = state
        self.updatedAt = updatedAt

    def advance(self, newState: str, now: datetime) -> bool:
        """DELIVERED/READ only ever move forward; returns True on change."""
        if READ_STATE_RANK[newState] <= READ_STATE_RANK[self.state]:
            return False
        self.state = newState
        self.updatedAt = now
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "messageId": str(self.messageId),
            "userId": str(self.userId),
            "state": self.state,
        }


def initialReadState() -> str:
    return READ_SENT


def deliveredState() -> str:
    return READ_DELIVERED


def readState() -> str:
    return READ_READ


class PinnedMessage(AggregateRoot):
    """§4 — pinned messages, managed by moderators."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        conversationId: uuid.UUID,
        messageId: uuid.UUID,
        pinnedBy: uuid.UUID,
        pinnedAt: datetime,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.conversationId = conversationId
        self.messageId = messageId
        self.pinnedBy = pinnedBy
        self.pinnedAt = pinnedAt

    def snapshot(self) -> dict[str, Any]:
        return {
            "messageId": str(self.messageId),
            "conversationId": str(self.conversationId),
            "pinnedBy": str(self.pinnedBy),
        }
