"""Credential aggregates — separated from User (Phase 07 §5).

Credential types (§5): password history, email/phone verification, MFA
secret, recovery code, API key, service credential, external identity.
Secrets are stored ONLY as hashes or secret-manager references — never raw
(invariant §35.10 / DoD 20).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId

CREDENTIAL_PASSWORD = "password"
CREDENTIAL_EMAIL_VERIFICATION = "emailVerification"
CREDENTIAL_PHONE_VERIFICATION = "phoneVerification"
CREDENTIAL_MFA_SECRET = "mfaSecret"
CREDENTIAL_RECOVERY_CODE = "recoveryCode"
CREDENTIAL_API_KEY = "apiKey"
CREDENTIAL_SERVICE_CREDENTIAL = "serviceCredential"
CREDENTIAL_EXTERNAL_IDENTITY = "externalIdentity"


class PasswordHistoryEntry(AggregateRoot):
    """One previous password hash (§23 password history)."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        passwordHash: str,
        createdAt: datetime,
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.passwordHash = passwordHash
        self.createdAt = createdAt

    def snapshot(self) -> dict[str, Any]:
        return {"id": str(self.id), "userId": str(self.userId)}


class VerificationToken(AggregateRoot):
    """Email / phone / activation verification (Phase 07 §26).

    Tokenized, time limited, single use, attempt counted; the hash is stored
    — the raw token exists only in the delivery channel.
    """

    CHANNEL_EMAIL = "email"
    CHANNEL_PHONE = "phone"
    CHANNEL_ACTIVATION = "activation"

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        channel: str,
        destination: str,
        tokenHash: str,
        expiresAt: datetime,
        *,
        attemptCount: int = 0,
        verifiedAt: datetime | None = None,
        createdAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.channel = channel
        self.destination = destination
        self.tokenHash = tokenHash
        self.expiresAt = expiresAt
        self.attemptCount = attemptCount
        self.verifiedAt = verifiedAt
        self.createdAt = createdAt

    @staticmethod
    def issue(
        userId: uuid.UUID,
        channel: str,
        destination: str,
        tokenHash: str,
        now: datetime,
        ttlMinutes: int,
    ) -> VerificationToken:
        from datetime import timedelta

        return VerificationToken(
            id=newId(),
            userId=userId,
            channel=channel,
            destination=destination,
            tokenHash=tokenHash,
            expiresAt=now + timedelta(minutes=ttlMinutes),
            createdAt=now,
        )

    def isExpiredAt(self, now: datetime) -> bool:
        return self.expiresAt <= now

    def isUsed(self) -> bool:
        return self.verifiedAt is not None

    def isUsableAt(self, now: datetime) -> bool:
        return not self.isUsed() and not self.isExpiredAt(now)

    def markVerified(self, now: datetime) -> None:
        self.verifiedAt = now

    def registerAttempt(self) -> None:
        self.attemptCount += 1

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "channel": self.channel,
            "destination": self.destination,
            "expiresAt": self.expiresAt.isoformat(),
            "verified": self.verifiedAt is not None,
        }


class PasswordResetToken(AggregateRoot):
    """Password recovery token (Phase 07 §25): tokenized · time limited ·
    single use · audited (auditing happens in the use case)."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        tokenHash: str,
        expiresAt: datetime,
        *,
        usedAt: datetime | None = None,
        createdAt: datetime | None = None,
        requestIp: str = "",
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.tokenHash = tokenHash
        self.expiresAt = expiresAt
        self.usedAt = usedAt
        self.createdAt = createdAt
        self.requestIp = requestIp

    @staticmethod
    def issue(
        userId: uuid.UUID,
        tokenHash: str,
        now: datetime,
        ttlMinutes: int,
        *,
        requestIp: str = "",
    ) -> PasswordResetToken:
        from datetime import timedelta

        return PasswordResetToken(
            id=newId(),
            userId=userId,
            tokenHash=tokenHash,
            expiresAt=now + timedelta(minutes=ttlMinutes),
            createdAt=now,
            requestIp=requestIp,
        )

    def isExpiredAt(self, now: datetime) -> bool:
        return self.expiresAt <= now

    def isUsed(self) -> bool:
        return self.usedAt is not None

    def isUsableAt(self, now: datetime) -> bool:
        return not self.isUsed() and not self.isExpiredAt(now)

    def markUsed(self, now: datetime) -> None:
        self.usedAt = now

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "userId": str(self.userId),
            "expiresAt": self.expiresAt.isoformat(),
            "used": self.usedAt is not None,
        }
