"""Session aggregate (Phase 07 §9) — trackable, revocable login session.

Token model (§7): short-lived **JWT access token** (claims only, §8) plus a
long-lived rotating **opaque refresh token** stored hashed on the session.
JWT is never the sole session mechanism (§7): every access-token
verification re-checks this session row, so revocation is instant
(invariant §35.4/5). Fields per §9: id, user, tenant, createdAt,
lastActivityAt, expiresAt, revokedAt, ipAddress, userAgent, device, status.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.events import DomainEvent

SESSION_ACTIVE = "active"
SESSION_REVOKED = "revoked"
SESSION_EXPIRED = "expired"


class Session(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        refreshTokenHash: str,
        issuedAt: datetime,
        expiresAt: datetime,
        *,
        lastActivityAt: datetime | None = None,
        revokedAt: datetime | None = None,
        ipAddress: str = "",
        userAgent: str = "",
        device: str = "",
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.tenantId = tenantId
        self.refreshTokenHash = refreshTokenHash
        self.issuedAt = issuedAt
        self.expiresAt = expiresAt
        self.lastActivityAt = lastActivityAt
        self.revokedAt = revokedAt
        self.ipAddress = ipAddress
        self.userAgent = userAgent
        self.device = device

    @staticmethod
    def start(
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        refreshTokenHash: str,
        now: datetime,
        ttlMinutes: int,
        *,
        ipAddress: str = "",
        userAgent: str = "",
        device: str = "",
    ) -> Session:
        session = Session(
            id=newId(),
            userId=userId,
            tenantId=tenantId,
            refreshTokenHash=refreshTokenHash,
            issuedAt=now,
            expiresAt=now + timedelta(minutes=ttlMinutes),
            lastActivityAt=now,
            ipAddress=ipAddress,
            userAgent=userAgent,
            device=device,
        )
        session.recordEvent(
            DomainEvent(
                name="sessionCreated",
                occurredAt=now,
                tenantId=tenantId,
                actorId=userId,
                payload={"ip": ipAddress, "device": device},
            )
        )
        return session

    # -- status (§9) ----------------------------------------------------------

    def statusAt(self, now: datetime) -> str:
        if self.revokedAt is not None:
            return SESSION_REVOKED
        if self.expiresAt <= now:
            return SESSION_EXPIRED
        return SESSION_ACTIVE

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

    def rotateRefreshToken(self, newHash: str, now: datetime) -> None:
        """Refresh-token rotation (§7): replace the hash inside the session."""
        self.refreshTokenHash = newHash
        self.lastActivityAt = now

    def touch(self, now: datetime) -> None:
        self.lastActivityAt = now

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "userId": str(self.userId),
            "tenantId": str(self.tenantId),
            "issuedAt": self.issuedAt.isoformat(),
            "lastActivityAt": self.lastActivityAt.isoformat() if self.lastActivityAt else None,
            "expiresAt": self.expiresAt.isoformat(),
            "revokedAt": self.revokedAt.isoformat() if self.revokedAt else None,
            "ipAddress": self.ipAddress,
            "userAgent": self.userAgent,
            "device": self.device,
        }
