"""Tenant aggregate root — top isolation boundary (§9 GLOBAL owner)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError
from apps.sharedKernel.domain.events import DomainEvent
from apps.tenancy.domain.valueObjects.tenantState import (
    TENANT_ACTIVE,
    TENANT_SUSPENDED,
    TenantCode,
    TenantStatus,
)


class Tenant(AggregateRoot):
    """A tenant of the platform: owns every tenant-scoped row (BR-TEN-001)."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        code: TenantCode,
        name: str,
        status: TenantStatus,
        createdAt: datetime,
        updatedAt: datetime | None = None,
        deletedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.code = code
        self.name = name
        self.status = status
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.deletedAt = deletedAt

    # -- factory (use-case step 4) ------------------------------------------

    @staticmethod
    def create(code: TenantCode, name: str, now: datetime) -> Tenant:
        tenant = Tenant(
            id=newId(),
            code=code,
            name=name.strip(),
            status=TenantStatus(TENANT_ACTIVE),
            createdAt=now,
        )
        tenant.recordEvent(
            DomainEvent(
                name="tenantCreated",
                occurredAt=now,
                tenantId=tenant.id,
                payload={"code": str(code), "name": tenant.name},
            )
        )
        return tenant

    # -- behaviour -----------------------------------------------------------

    def transitionTo(self, target: str, now: datetime, *, actorId: uuid.UUID | None = None) -> None:
        if not self.status.canTransitionTo(target):
            raise InvalidStateTransitionError(f"Tenant cannot move from {self.status} to {target}.")
        previous = str(self.status)
        self.status = TenantStatus(target)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="tenantStatusChanged",
                occurredAt=now,
                tenantId=self.id,
                actorId=actorId,
                payload={"from": previous, "to": target},
            )
        )

    def suspend(self, now: datetime, *, actorId: uuid.UUID | None = None) -> None:
        self.transitionTo(TENANT_SUSPENDED, now, actorId=actorId)

    def reactivate(self, now: datetime, *, actorId: uuid.UUID | None = None) -> None:
        self.transitionTo(TENANT_ACTIVE, now, actorId=actorId)

    def isActive(self) -> bool:
        return str(self.status) == TENANT_ACTIVE

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "code": str(self.code),
            "name": self.name,
            "status": str(self.status),
        }
