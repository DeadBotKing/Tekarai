"""OfficialLetter aggregate (Phase 08 §16) — a DEDICATED domain model.

Official letters are formal, reference-numbered, approval-driven documents
— never ``Message(messageType="LETTER")`` (§16). Attachments/signatures
delegate to the future Documents/approval flow subsystems; this aggregate owns
identity, lifecycle and the audit trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.communication.domain.valueObjects.communicationTypes import (
    LETTER_DRAFT,
    LETTER_TRANSITIONS,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError

LETTER_REFERENCE_PATTERN = r"^\d{4}-\d{6}$"  # e.g. 2026-000123


class OfficialLetter(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        referenceNumber: str,
        senderId: uuid.UUID,
        recipientId: uuid.UUID,
        subject: str,
        createdAt: datetime,
        *,
        body: str = "",
        recipientOrganization: str = "",
        recipientUnit: str = "",
        letterStatus: str = LETTER_DRAFT,
        approvedBy: uuid.UUID | None = None,
        signedBy: uuid.UUID | None = None,
        dispatchedAt: datetime | None = None,
        receivedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.referenceNumber = referenceNumber
        self.senderId = senderId
        self.recipientId = recipientId
        self.subject = subject.strip()
        self.body = body
        self.recipientOrganization = recipientOrganization.strip()
        self.recipientUnit = recipientUnit.strip()
        self.createdAt = createdAt
        self.letterStatus = letterStatus
        self.approvedBy = approvedBy
        self.signedBy = signedBy
        self.dispatchedAt = dispatchedAt
        self.receivedAt = receivedAt

    # -- factory -----------------------------------------------------------------

    @staticmethod
    def draft(
        tenantId: uuid.UUID,
        senderId: uuid.UUID,
        recipientId: uuid.UUID,
        subject: str,
        referenceNumber: str,
        now: datetime,
        *,
        body: str = "",
        recipientOrganization: str = "",
        recipientUnit: str = "",
    ) -> OfficialLetter:
        if not subject.strip():
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Letter subject is required.", fieldErrors={"subject": "empty"}
            )
        letter = OfficialLetter(
            id=newId(),
            tenantId=tenantId,
            referenceNumber=referenceNumber,
            senderId=senderId,
            recipientId=recipientId,
            subject=subject,
            createdAt=now,
            body=body,
            recipientOrganization=recipientOrganization,
            recipientUnit=recipientUnit,
        )
        letter.recordEvent(
            DomainEvent(
                name="letterCreated",
                occurredAt=now,
                tenantId=tenantId,
                actorId=senderId,
                payload={"referenceNumber": referenceNumber},
            )
        )
        return letter

    # -- workflow (§16) -------------------------------------------------------------

    def transitionTo(self, target: str, now: datetime) -> None:
        allowed = LETTER_TRANSITIONS.get(self.letterStatus, ())
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"Letter cannot move {self.letterStatus} → {target}."
            )
        self.letterStatus = target
        self.recordEvent(
            DomainEvent(
                name=f"letter{target.capitalize()}",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"referenceNumber": self.referenceNumber},
            )
        )

    def approve(self, now: datetime, approvedBy: uuid.UUID) -> None:
        self.transitionTo("APPROVED", now)
        self.approvedBy = approvedBy

    def sign(self, now: datetime, signedBy: uuid.UUID) -> None:
        self.transitionTo("SIGNED", now)
        self.signedBy = signedBy

    def dispatch(self, now: datetime) -> None:
        self.transitionTo("DISPATCHED", now)
        self.dispatchedAt = now

    def markReceived(self, now: datetime) -> None:
        self.transitionTo("RECEIVED", now)
        self.receivedAt = now

    def isDispatched(self) -> bool:
        return self.dispatchedAt is not None

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "referenceNumber": self.referenceNumber,
            "subject": self.subject,
            "status": self.letterStatus,
            "senderId": str(self.senderId),
            "recipientId": str(self.recipientId),
        }
