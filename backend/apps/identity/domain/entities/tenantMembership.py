"""TenantMembership (Phase 07 §11–§12) — a user may belong to many tenants.

One user can be ACTIVE in tenant A and SUSPENDED in tenant B (§12): the
membership — not the user — carries the per-tenant status. ``isPrimary``
marks the default tenant of the login screen; ``defaultRole`` is the role
code assigned on joining. Re-joining after leaving creates a new row
(history preserved, Phase 04 §36 pattern).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError
from apps.sharedKernel.domain.events import DomainEvent

MEMBERSHIP_ACTIVE = "active"
MEMBERSHIP_SUSPENDED = "suspended"
MEMBERSHIP_REMOVED = "removed"

MEMBERSHIP_TRANSITIONS: dict[str, tuple[str, ...]] = {
    MEMBERSHIP_ACTIVE: (MEMBERSHIP_SUSPENDED, MEMBERSHIP_REMOVED),
    MEMBERSHIP_SUSPENDED: (MEMBERSHIP_ACTIVE, MEMBERSHIP_REMOVED),
    MEMBERSHIP_REMOVED: (),
}


class TenantMembership(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        joinedAt: datetime,
        *,
        status: str = MEMBERSHIP_ACTIVE,
        isPrimary: bool = False,
        defaultRole: str = "",
        leftAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.tenantId = tenantId
        self.joinedAt = joinedAt
        self.status = status
        self.isPrimary = isPrimary
        self.defaultRole = defaultRole
        self.leftAt = leftAt

    @staticmethod
    def establish(
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        now: datetime,
        *,
        defaultRole: str = "member",
        isPrimary: bool = False,
    ) -> TenantMembership:
        membership = TenantMembership(
            id=newId(),
            userId=userId,
            tenantId=tenantId,
            joinedAt=now,
            defaultRole=defaultRole,
            isPrimary=isPrimary,
        )
        membership.recordEvent(
            DomainEvent(
                name="userAssignedToTenant",
                occurredAt=now,
                tenantId=tenantId,
                actorId=userId,
                payload={"defaultRole": defaultRole},
            )
        )
        return membership

    def transitionTo(self, target: str, now: datetime) -> None:
        if target not in MEMBERSHIP_TRANSITIONS[self.status]:
            raise InvalidStateTransitionError(
                f"Membership cannot move from {self.status} to {target}."
            )
        previous = self.status
        self.status = target
        if target == MEMBERSHIP_REMOVED and self.leftAt is None:
            self.leftAt = now
        self.recordEvent(
            DomainEvent(
                name="membershipSuspended"
                if target == MEMBERSHIP_SUSPENDED
                else "membershipRemoved",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"from": previous, "to": target},
            )
        )

    def suspend(self, now: datetime) -> None:
        self.transitionTo(MEMBERSHIP_SUSPENDED, now)

    def reactivate(self, now: datetime) -> None:
        self.transitionTo(MEMBERSHIP_ACTIVE, now)

    def remove(self, now: datetime) -> None:
        self.transitionTo(MEMBERSHIP_REMOVED, now)

    def isActive(self) -> bool:
        return self.status == MEMBERSHIP_ACTIVE

    def isSuspended(self) -> bool:
        return self.status == MEMBERSHIP_SUSPENDED

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "userId": str(self.userId),
            "tenantId": str(self.tenantId),
            "status": self.status,
            "joinedAt": self.joinedAt.isoformat(),
            "leftAt": self.leftAt.isoformat() if self.leftAt else None,
            "isPrimary": self.isPrimary,
            "defaultRole": self.defaultRole,
        }
