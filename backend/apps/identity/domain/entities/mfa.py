"""MFA factor aggregate (Phase 07 §24) — MFA-ready architecture.

Methods (§24): TOTP · Email OTP · SMS OTP · WebAuthn/Passkeys. V1 implements
the TOTP factor end-to-end (RFC 6238, verified by the pure-domain
``totpService``); the other methods plug in as new factor types without
touching the login flow. Enable/disable can be driven per system / tenant /
user via ``MFAPolicy`` settings.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.events import DomainEvent

MFA_TOTP = "totp"
MFA_EMAIL_OTP = "emailOtp"
MFA_SMS_OTP = "smsOtp"
MFA_WEBAUTHN = "webAuthn"

FACTOR_PENDING = "pending"
FACTOR_ACTIVE = "active"
FACTOR_DISABLED = "disabled"


class MfaFactor(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        factorType: str,
        secretRef: str,
        createdAt: datetime,
        *,
        status: str = FACTOR_PENDING,
        confirmedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.factorType = factorType
        self.secretRef = secretRef  # encrypted secret / secret-manager reference
        self.status = status
        self.createdAt = createdAt
        self.confirmedAt = confirmedAt

    @staticmethod
    def beginSetup(userId: uuid.UUID, factorType: str, secretRef: str, now: datetime) -> MfaFactor:
        factor = MfaFactor(
            id=newId(), userId=userId, factorType=factorType, secretRef=secretRef, createdAt=now
        )
        return factor

    def confirm(self, now: datetime) -> None:
        self.status = FACTOR_ACTIVE
        self.confirmedAt = now
        self.recordEvent(
            DomainEvent(name="mfaEnabled", occurredAt=now, payload={"factorType": self.factorType})
        )

    def disable(self, now: datetime) -> None:
        self.status = FACTOR_DISABLED
        self.recordEvent(
            DomainEvent(name="mfaDisabled", occurredAt=now, payload={"factorType": self.factorType})
        )

    def isActive(self) -> bool:
        return self.status == FACTOR_ACTIVE

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "factorType": self.factorType,
            "status": self.status,
            "confirmedAt": self.confirmedAt.isoformat() if self.confirmedAt else None,
        }


class RecoveryCode(AggregateRoot):
    """Single-use recovery code (§5) — hashed at rest, consumed on use."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        codeHash: str,
        createdAt: datetime,
        *,
        usedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.codeHash = codeHash
        self.createdAt = createdAt
        self.usedAt = usedAt

    def isUsable(self) -> bool:
        return self.usedAt is None

    def markUsed(self, now: datetime) -> None:
        self.usedAt = now

    def snapshot(self) -> dict[str, Any]:
        return {"id": str(self.id), "used": self.usedAt is not None}
