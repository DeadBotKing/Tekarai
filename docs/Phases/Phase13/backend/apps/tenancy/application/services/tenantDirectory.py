"""TenantDirectory — the public cross-context contract of Tenancy (RULE F).

Other contexts (e.g. Identity at login) resolve tenants ONLY through this
application service, never by importing tenancy domain/infrastructure.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class TenantSummary:
    id: str
    code: str
    name: str
    status: str
    active: bool


class TenantDirectory:
    def __init__(self, repository) -> None:  # noqa: ANN001 — tenancy contract
        self.repository = repository

    def getByCode(self, code: str) -> TenantSummary | None:
        tenant = self.repository.getByCode(code)
        return summarize(tenant) if tenant else None

    def getById(self, tenantId: uuid.UUID) -> TenantSummary | None:
        tenant = self.repository.getById(tenantId)
        return summarize(tenant) if tenant else None


def defaultTenantDirectory() -> TenantDirectory:
    """Composition facade: late-binds the ORM repository (Phase 06 §34).

    The application layer owns the public contract; the implementation is
    bound at call time so the import direction of every consumer stays
    ``consumer → apps.tenancy.application`` (RULE F).
    """
    from apps.tenancy.infrastructure.repositories.tenantRepositoryImpl import (
        TenantRepositoryDjango,
    )

    return TenantDirectory(TenantRepositoryDjango())


def summarize(tenant) -> TenantSummary:  # noqa: ANN001 — tenancy contract
    return TenantSummary(
        id=str(tenant.id),
        code=str(tenant.code),
        name=tenant.name,
        status=str(tenant.status),
        active=str(tenant.status) == "active",
    )
