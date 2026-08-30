"""TenantMembership — links a user to a tenant (§4 "Assign User to Tenant").

One ACTIVE membership per user per tenant (BR pattern of Phase 04 §36:
re-joining after leaving creates a new row — history preserved).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.events import DomainEvent


class TenantMembership(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        userId: uuid.UUID,
        tenantId: uuid.UUID,
        joinedAt: datetime,
        leftAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.userId = userId
        self.tenantId = tenantId
        self.joinedAt = joinedAt
        self.leftAt = leftAt

    @staticmethod
    def establish(userId: uuid.UUID, tenantId: uuid.UUID, now: datetime) -> TenantMembership:
        membership = TenantMembership(id=newId(), userId=userId, tenantId=tenantId, joinedAt=now)
        membership.recordEvent(
            DomainEvent(
                name="userAssignedToTenant",
                occurredAt=now,
                tenantId=tenantId,
                actorId=userId,
                payload={},
            )
        )
        return membership

    def isActive(self) -> bool:
        return self.leftAt is None

    def close(self, now: datetime) -> None:
        if self.leftAt is None:
            self.leftAt = now

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "userId": str(self.userId),
            "tenantId": str(self.tenantId),
            "joinedAt": self.joinedAt.isoformat(),
            "leftAt": self.leftAt.isoformat() if self.leftAt else None,
        }
