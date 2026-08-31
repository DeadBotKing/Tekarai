"""ConversationParticipant aggregate (Phase 08 §3.2, §6).

Membership with roles (OWNER/ADMIN/MODERATOR/MEMBER/GUEST), full history
(joinedAt/leftAt — §6 "complete membership history"), mute + notification
level and the read watermark (§32).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.communication.domain.valueObjects.communicationTypes import (
    NOTIFICATION_LEVELS,
    NOTIFY_ALL,
    PARTICIPANT_ADMIN,
    PARTICIPANT_MODERATOR,
    PARTICIPANT_MEMBER,
    PARTICIPANT_OWNER,
    PARTICIPANT_ROLES,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId


class ConversationParticipant(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        conversationId: uuid.UUID,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        role: str,
        joinedAt: datetime,
        *,
        leftAt: datetime | None = None,
        isMuted: bool = False,
        notificationLevel: str = NOTIFY_ALL,
        lastReadMessageId: uuid.UUID | None = None,
        invitedBy: uuid.UUID | None = None,
    ) -> None:
        super().__init__(id)
        if role not in PARTICIPANT_ROLES:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unknown participant role.", fieldErrors={"role": role}
            )
        if notificationLevel not in NOTIFICATION_LEVELS:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unknown notification level.",
                fieldErrors={"notificationLevel": notificationLevel},
            )
        self.conversationId = conversationId
        self.tenantId = tenantId
        self.userId = userId
        self.role = role
        self.joinedAt = joinedAt
        self.leftAt = leftAt
        self.isMuted = isMuted
        self.notificationLevel = notificationLevel
        self.lastReadMessageId = lastReadMessageId
        self.invitedBy = invitedBy

    # -- factories -----------------------------------------------------------

    @staticmethod
    def establish(
        conversationId: uuid.UUID,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        role: str,
        now: datetime,
        *,
        invitedBy: uuid.UUID | None = None,
    ) -> ConversationParticipant:
        participant = ConversationParticipant(
            id=newId(),
            conversationId=conversationId,
            tenantId=tenantId,
            userId=userId,
            role=role,
            joinedAt=now,
            invitedBy=invitedBy,
        )
        participant.recordEvent(
            DomainEvent(
                name="participantJoined",
                occurredAt=now,
                tenantId=tenantId,
                actorId=userId,
                payload={"conversationId": str(conversationId), "role": role},
            )
        )
        return participant

    # -- behaviour -----------------------------------------------------------

    def leave(self, now: datetime) -> None:
        if self.leftAt is not None:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Participant already left.")
        if self.role == PARTICIPANT_OWNER:
            from apps.sharedKernel.domain.errors import BusinessRuleViolationError

            raise BusinessRuleViolationError(
                "The owner cannot leave; transfer ownership first.",
                ruleId="PHASE8-BR_OwnerCannotLeave",
            )
        self.leftAt = now
        self.recordEvent(
            DomainEvent(
                name="participantLeft",
                occurredAt=now,
                tenantId=self.tenantId,
                actorId=self.userId,
                payload={"conversationId": str(self.conversationId)},
            )
        )

    def remove(self, now: datetime, removedBy: uuid.UUID) -> None:
        """Moderated removal (§6) — history preserved via leftAt."""
        if self.leftAt is not None:
            from apps.sharedKernel.domain.errors import ConflictError

            raise ConflictError("Participant already removed.")
        if self.role == PARTICIPANT_OWNER:
            from apps.sharedKernel.domain.errors import PermissionDeniedError

            raise PermissionDeniedError(action="participant.remove")
        del removedBy
        self.leftAt = now
        self.recordEvent(
            DomainEvent(
                name="participantLeft",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={
                    "conversationId": str(self.conversationId),
                    "removed": True,
                },
            )
        )

    def changeRole(self, newRole: str, now: datetime) -> None:
        if newRole not in PARTICIPANT_ROLES:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unknown participant role.", fieldErrors={"role": newRole}
            )
        if self.role == PARTICIPANT_OWNER or newRole == PARTICIPANT_OWNER:
            from apps.sharedKernel.domain.errors import PermissionDeniedError

            raise PermissionDeniedError(
                "Ownership transfer is a dedicated operation.",
                action="participant.changeRole",
            )
        self.role = newRole
        del now

    def setPreferences(
        self, *, isMuted: bool | None, notificationLevel: str | None
    ) -> None:
        if notificationLevel is not None and notificationLevel not in NOTIFICATION_LEVELS:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unknown notification level.",
                fieldErrors={"notificationLevel": notificationLevel},
            )
        if isMuted is not None:
            self.isMuted = isMuted
        if notificationLevel is not None:
            self.notificationLevel = notificationLevel

    def markRead(self, messageId: uuid.UUID) -> None:
        self.lastReadMessageId = messageId

    def isActive(self) -> bool:
        return self.leftAt is None

    def isModerator(self) -> bool:
        return self.role in (PARTICIPANT_OWNER, PARTICIPANT_ADMIN, PARTICIPANT_MODERATOR)

    def isAdmin(self) -> bool:
        return self.role in (PARTICIPANT_OWNER, PARTICIPANT_ADMIN)

    def isMember(self) -> bool:
        return self.leftAt is None and self.role != ""

    def effectiveRole(self) -> str:
        return self.role or PARTICIPANT_MEMBER

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "conversationId": str(self.conversationId),
            "userId": str(self.userId),
            "role": self.role,
            "isMuted": self.isMuted,
            "notificationLevel": self.notificationLevel,
            "isActive": self.isActive(),
        }
