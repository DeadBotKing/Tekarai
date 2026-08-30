"""Push device registration (Phase 09 §15)."""

from __future__ import annotations

import uuid
from datetime import datetime

from apps.sharedKernel.domain.entities import AggregateRoot
from apps.sharedKernel.domain.errors import ConflictError, ValidationFailedError

PLATFORMS = ("IOS", "ANDROID", "WEB", "DESKTOP", "OTHER")


class NotificationDevice(AggregateRoot):
    """§15 — never assume one user has one device; tokens are sensitive
    (§33) and live only in this aggregate + its table."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        platform: str,
        deviceIdentifier: str,
        pushToken: str,
        provider: str,
        *,
        createdAt: datetime | None = None,
        lastSeenAt: datetime | None = None,
        revokedAt: datetime | None = None,
        isActive: bool = True,
    ) -> None:
        super().__init__(id)
        if platform not in PLATFORMS:
            raise ValidationFailedError(
                "Unknown device platform.", fieldErrors={"platform": platform}
            )
        if not deviceIdentifier.strip() or not pushToken.strip():
            raise ValidationFailedError(
                "Device identifier and push token are required.",
                fieldErrors={"deviceIdentifier": "required"},
            )
        self.tenantId = tenantId
        self.userId = userId
        self.platform = platform
        self.deviceIdentifier = deviceIdentifier
        self.pushToken = pushToken
        self.provider = provider
        self.createdAt = createdAt or datetime.now()
        self.lastSeenAt = lastSeenAt
        self.revokedAt = revokedAt
        self.isActive = isActive

    def touch(self, now: datetime) -> None:
        self.lastSeenAt = now

    def revoke(self, now: datetime) -> None:
        """§49 — a revoked device must stop receiving push immediately."""
        if self.revokedAt is not None:
            return  # idempotent
        self.revokedAt = now
        self.isActive = False

    def reactivate(self, now: datetime, pushToken: str) -> None:
        if self.revokedAt is None:
            raise ConflictError("Device is not revoked.")
        self.revokedAt = None
        self.isActive = True
        self.pushToken = pushToken
        self.lastSeenAt = now
