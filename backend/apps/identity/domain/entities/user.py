"""User aggregate — identity record of a person (BR-USR-001: the identity
is deliberately separate from any workforce/staff record)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.identity.domain.valueObjects.userState import USER_ACTIVE, UserStatus
from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError
from apps.sharedKernel.domain.events import DomainEvent


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
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.deletedAt = deletedAt

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        username: str,
        email: str,
        passwordHash: str,
        displayName: str,
        now: datetime,
        *,
        status: str = USER_ACTIVE,
    ) -> User:
        user = User(
            id=newId(),
            tenantId=tenantId,
            username=username,
            email=email,
            passwordHash=passwordHash,
            displayName=displayName or username,
            status=UserStatus(status),
            createdAt=now,
        )
        user.recordEvent(
            DomainEvent(
                name="userCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"username": user.username, "email": user.email},
            )
        )
        return user

    def transitionTo(self, target: str, now: datetime) -> None:
        if not self.status.canTransitionTo(target):
            raise InvalidStateTransitionError(f"User cannot move from {self.status} to {target}.")
        previous = str(self.status)
        self.status = UserStatus(target)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="userStatusChanged",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"from": previous, "to": target},
            )
        )

    def isActive(self) -> bool:
        return str(self.status) == USER_ACTIVE

    def snapshot(self, *, includeSecrets: bool = False) -> dict[str, Any]:
        view = {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "username": self.username,
            "email": self.email,
            "displayName": self.displayName,
            "status": str(self.status),
        }
        if includeSecrets:  # only for internal audit comparisons, never logs
            view["passwordHash"] = "***"
        return view
