"""Conversation aggregate (Phase 08 §3.1, §4, §5, §6).

A conversation is the communication container for DIRECT chats, GROUP
chats, CHANNELS and MEETING rooms. Direct chats carry a deterministic
``directKey`` so the same two users can never accumulate duplicate
conversations (§5). Channels get profile fields (topic/visibility) stored
beside the conversation row (§4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.communication.domain.valueObjects.communicationTypes import (
    CONVERSATION_CHANNEL,
    CONVERSATION_DIRECT,
    ConversationType,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId


class Conversation(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        conversationType: str,
        createdAt: datetime,
        *,
        createdBy: uuid.UUID | None = None,
        name: str = "",
        description: str = "",
        directKey: str = "",
        isActive: bool = True,
        archivedAt: datetime | None = None,
        updatedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.conversationType = ConversationType(conversationType).value
        self.createdAt = createdAt
        self.createdBy = createdBy
        self.name = name.strip()
        self.description = description.strip()
        self.directKey = directKey
        self.isActive = isActive
        self.archivedAt = archivedAt
        self.updatedAt = updatedAt

    # -- factories -----------------------------------------------------------

    @staticmethod
    def createDirect(
        tenantId: uuid.UUID,
        userA: uuid.UUID,
        userB: uuid.UUID,
        now: datetime,
    ) -> Conversation:
        """§5 — exactly two participants, deterministic dedup key."""
        if userA == userB:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "A direct conversation needs two different users.",
                fieldErrors={"participants": "same user twice"},
            )
        from apps.communication.domain.services.communicationRules import directKeyOf

        conversation = Conversation(
            id=newId(),
            tenantId=tenantId,
            conversationType=CONVERSATION_DIRECT,
            createdAt=now,
            createdBy=userA,
            directKey=directKeyOf(userA, userB),
        )
        conversation.recordEvent(
            DomainEvent(
                name="conversationCreated",
                occurredAt=now,
                tenantId=tenantId,
                actorId=userA,
                payload={"type": CONVERSATION_DIRECT},
            )
        )
        return conversation

    @staticmethod
    def createGroup(
        tenantId: uuid.UUID,
        createdBy: uuid.UUID,
        name: str,
        now: datetime,
        *,
        description: str = "",
    ) -> Conversation:
        conversation = Conversation(
            id=newId(),
            tenantId=tenantId,
            conversationType=ConversationType("GROUP").value,
            createdAt=now,
            createdBy=createdBy,
            name=name,
            description=description,
        )
        conversation.recordEvent(
            DomainEvent(
                name="conversationCreated",
                occurredAt=now,
                tenantId=tenantId,
                actorId=createdBy,
                payload={"type": "GROUP", "name": conversation.name},
            )
        )
        return conversation

    @staticmethod
    def createChannel(
        tenantId: uuid.UUID,
        createdBy: uuid.UUID,
        name: str,
        now: datetime,
        *,
        description: str = "",
        code: str = "",
    ) -> Conversation:
        conversation = Conversation(
            id=newId(),
            tenantId=tenantId,
            conversationType=CONVERSATION_CHANNEL,
            createdAt=now,
            createdBy=createdBy,
            name=name,
            description=description,
        )
        conversation.code = code  # channel profile (§4), set by the use case
        conversation.recordEvent(
            DomainEvent(
                name="conversationCreated",
                occurredAt=now,
                tenantId=tenantId,
                actorId=createdBy,
                payload={"type": CONVERSATION_CHANNEL, "name": conversation.name},
            )
        )
        return conversation

    # -- behaviour -----------------------------------------------------------

    def archive(self, now: datetime) -> None:
        if self.archivedAt is not None:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Conversation is already archived.")
        self.archivedAt = now
        self.isActive = False
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="conversationArchived",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"conversationId": str(self.id)},
            )
        )

    def updateProfile(
        self, *, name: str | None, description: str | None, now: datetime
    ) -> None:
        if name is not None and name.strip():
            self.name = name.strip()
        if description is not None:
            self.description = description.strip()
        self.updatedAt = now

    def isActiveAt(self, now: datetime) -> bool:
        del now  # archived forever once archivedAt set; kept for symmetry
        return self.isActive and self.archivedAt is None

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "type": self.conversationType,
            "name": self.name,
            "directKey": self.directKey,
            "isActive": self.isActive,
        }
