"""Service Account aggregate (Phase 07 §21).

For agents, integrations, automation, background workers, external systems
and AI services. Not a human user (§21): separate aggregate with its own
credentials, permissions, roles, scopes and audit identity — it never
pretends to be an employee or a person.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError
from apps.sharedKernel.domain.events import DomainEvent

SERVICE_ACCOUNT_ACTIVE = "active"
SERVICE_ACCOUNT_DISABLED = "disabled"

SERVICE_ACCOUNT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    SERVICE_ACCOUNT_ACTIVE: (SERVICE_ACCOUNT_DISABLED,),
    SERVICE_ACCOUNT_DISABLED: (SERVICE_ACCOUNT_ACTIVE,),
}


class ServiceAccount(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        code: str,
        name: str,
        description: str,
        createdAt: datetime,
        *,
        status: str = SERVICE_ACCOUNT_ACTIVE,
        scopes: tuple[str, ...] = (),
        disabledAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.code = code.strip().lower()
        self.name = name.strip()
        self.description = description.strip()
        self.status = status
        self.scopes = tuple(scopes)
        self.createdAt = createdAt
        self.disabledAt = disabledAt

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        code: str,
        name: str,
        description: str,
        now: datetime,
        *,
        scopes: tuple[str, ...] = (),
    ) -> ServiceAccount:
        account = ServiceAccount(
            id=newId(),
            tenantId=tenantId,
            code=code,
            name=name,
            description=description,
            createdAt=now,
            scopes=scopes,
        )
        account.recordEvent(
            DomainEvent(
                name="serviceAccountCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"code": account.code},
            )
        )
        return account

    def transitionTo(self, target: str, now: datetime) -> None:
        if target not in SERVICE_ACCOUNT_TRANSITIONS[self.status]:
            raise InvalidStateTransitionError(
                f"Service account cannot move from {self.status} to {target}."
            )
        previous = self.status
        self.status = target
        self.disabledAt = now if target == SERVICE_ACCOUNT_DISABLED else None
        self.recordEvent(
            DomainEvent(
                name="serviceAccountDisabled" if target == "disabled" else "serviceAccountEnabled",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"from": previous, "to": target},
            )
        )

    def isActive(self) -> bool:
        return self.status == SERVICE_ACCOUNT_ACTIVE

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "scopes": list(self.scopes),
        }
