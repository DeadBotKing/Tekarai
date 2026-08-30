"""Session aggregate — opaque bearer token, hashed at rest (BR-SEC-004).

Token lifecycle: issued at login → sliding use → explicit revoke at logout
or expiry sweep. Refresh rotates the token inside the same aggregate
(ADR-019: JWT provider can replace this behind the same repository).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.events import DomainEvent


class Session(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        tokenHash: str,
        issuedAt: datetime,
        expiresAt: datetime,
        lastUsedAt: datetime | None = None,
        revokedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.tenantId = tenantId
        self.tokenHash = tokenHash
        self.issuedAt = issuedAt
        self.expiresAt = expiresAt
        self.lastUsedAt = lastUsedAt
        self.revokedAt = revokedAt

    @staticmethod
    def issue(
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        tokenHash: str,
        now: datetime,
        ttlMinutes: int,
    ) -> Session:
        session = Session(
            id=newId(),
            userId=userId,
            tenantId=tenantId,
            tokenHash=tokenHash,
            issuedAt=now,
            expiresAt=now + timedelta(minutes=ttlMinutes),
        )
        session.recordEvent(
            DomainEvent(
                name="sessionIssued",
                occurredAt=now,
                tenantId=tenantId,
                actorId=userId,
                payload={},
            )
        )
        return session

    def isValidAt(self, now: datetime) -> bool:
        return self.revokedAt is None and self.expiresAt > now

    def isExpiredAt(self, now: datetime) -> bool:
        return self.revokedAt is None and self.expiresAt <= now

    def revoke(self, now: datetime) -> None:
        if self.revokedAt is None:
            self.revokedAt = now
            self.recordEvent(
                DomainEvent(
                    name="sessionRevoked",
                    occurredAt=now,
                    tenantId=self.tenantId,
                    actorId=self.userId,
                    payload={},
                )
            )

    def touch(self, now: datetime) -> None:
        self.lastUsedAt = now

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "userId": str(self.userId),
            "tenantId": str(self.tenantId),
            "issuedAt": self.issuedAt.isoformat(),
            "expiresAt": self.expiresAt.isoformat(),
            "revokedAt": self.revokedAt.isoformat() if self.revokedAt else None,
        }
