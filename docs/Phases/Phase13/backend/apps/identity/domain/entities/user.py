"""User aggregate — digital identity of a person or service (Phase 07 §2/§4).

Identity ≠ employment (§2): a User may be a customer, contractor, external
consultant, supplier, system operator, AI agent or service account — with no
employee record anywhere. Stable identity fields per §4; security bookkeeping
(lastLoginAt, passwordChangedAt, failedLoginCount, lockedUntil) lives here so
login security (§10) never depends on a bare isActive flag (§3).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from apps.identity.domain.valueObjects.userState import (
    LOCKABLE_STATUSES,
    USER_ACTIVE,
    USER_INVITED,
    USER_PENDING_ACTIVATION,
    UserStatus,
)
from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError
from apps.sharedKernel.domain.events import DomainEvent
from apps.sharedKernel.domain.valueObjects import EmailAddress

USER_KIND_HUMAN = "human"
USER_KIND_SERVICE = "service"


class User(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        username: str,
        email: str,
        passwordHash: str,
        displayName: str,
        status: UserStatus,
        createdAt: datetime,
        *,
        kind: str = USER_KIND_HUMAN,
        phone: str = "",
        lastLoginAt: datetime | None = None,
        passwordChangedAt: datetime | None = None,
        failedLoginCount: int = 0,
        lockedUntil: datetime | None = None,
        expiresAt: datetime | None = None,
        updatedAt: datetime | None = None,
        deletedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.username = username.strip().lower()
        self.email = email.strip().lower()
        self.passwordHash = passwordHash
        self.displayName = displayName.strip()
        self.status = status
        self.kind = kind
        self.phone = phone.strip()
        self.createdAt = createdAt
        self.lastLoginAt = lastLoginAt
        self.passwordChangedAt = passwordChangedAt
        self.failedLoginCount = failedLoginCount
        self.lockedUntil = lockedUntil
        self.expiresAt = expiresAt
        self.updatedAt = updatedAt
        self.deletedAt = deletedAt

    # -- factories -----------------------------------------------------------

    @staticmethod
    def register(
        tenantId: uuid.UUID,
        username: str,
        email: str,
        passwordHash: str,
        displayName: str,
        now: datetime,
        *,
        status: str = USER_ACTIVE,
        kind: str = USER_KIND_HUMAN,
        phone: str = "",
    ) -> User:
        """RegisterUser (§31) — INVITED by default; admin creation is ACTIVE."""
        EmailAddress(email)
        user = User(
            id=newId(),
            tenantId=tenantId,
            username=username,
            email=email,
            passwordHash=passwordHash,
            displayName=displayName or username,
            status=UserStatus(status),
            createdAt=now,
            kind=kind,
            phone=phone,
            passwordChangedAt=now,
        )
        user.recordEvent(
            DomainEvent(
                name="userRegistered" if status == USER_INVITED else "userCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"username": user.username, "status": status},
            )
        )
        return user

    # -- lifecycle (§3) ------------------------------------------------------

    def transitionTo(self, target: str, now: datetime) -> None:
        if not self.status.canTransitionTo(target):
            raise InvalidStateTransitionError(f"User cannot move from {self.status} to {target}.")
        previous = str(self.status)
        self.status = UserStatus(target)
        self.updatedAt = now
        eventName = {
            "active": "userActivated",
            "suspended": "userSuspended",
            "disabled": "userDisabled",
        }.get(target, "userStatusChanged")
        self.recordEvent(
            DomainEvent(
                name=eventName,
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"from": previous, "to": target},
            )
        )

    def activate(self, now: datetime) -> None:
        self.transitionTo(USER_ACTIVE, now)

    def inviteToActivation(self, now: datetime) -> None:
        self.transitionTo(USER_PENDING_ACTIVATION, now)

    def isActive(self) -> bool:
        return str(self.status) == USER_ACTIVE

    def isServiceKind(self) -> bool:
        return self.kind == USER_KIND_SERVICE

    # -- login security (§10) -------------------------------------------------

    def isLockedAt(self, now: datetime) -> bool:
        return self.lockedUntil is not None and self.lockedUntil > now

    def isExpiredAt(self, now: datetime) -> bool:
        return self.expiresAt is not None and self.expiresAt <= now

    def registerFailedLogin(
        self, now: datetime, *, maxFailedAttempts: int, lockMinutes: int
    ) -> bool:
        """Count a failure; lock the account when the threshold trips (§10).

        Returns True when this call caused the lock transition.
        """
        self.failedLoginCount += 1
        if self.failedLoginCount >= maxFailedAttempts and str(self.status) in LOCKABLE_STATUSES:
            self.lockedUntil = now + timedelta(minutes=lockMinutes)
            self.failedLoginCount = 0
            self.recordEvent(
                DomainEvent(
                    name="accountLocked",
                    occurredAt=now,
                    tenantId=self.tenantId,
                    payload={"lockedUntil": self.lockedUntil.isoformat()},
                )
            )
            return True
        return False

    def registerSuccessfulLogin(self, now: datetime) -> None:
        self.lastLoginAt = now
        self.failedLoginCount = 0
        self.lockedUntil = None

    def unlock(self, now: datetime) -> None:
        self.lockedUntil = None
        self.failedLoginCount = 0
        self.updatedAt = now

    def changePassword(self, passwordHash: str, now: datetime) -> None:
        self.passwordHash = passwordHash
        self.passwordChangedAt = now
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="passwordChanged",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={},
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "username": self.username,
            "email": self.email,
            "displayName": self.displayName,
            "status": str(self.status),
            "kind": self.kind,
            "phone": self.phone,
        }
