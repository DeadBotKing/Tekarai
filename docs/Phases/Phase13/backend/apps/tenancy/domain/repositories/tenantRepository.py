"""TenantRepository contract (Phase 06 §10, Phase 5 §10).

The domain defines the interface; infrastructure implements it with the ORM.
List signatures carry tenant scope explicitly (§10: every selector carries
its scope — never a bare ``list()``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from apps.tenancy.domain.entities.tenant import Tenant


@dataclass(frozen=True)
class TenantFilters:
    status: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class TenantPage:
    items: list[Tenant]
    totalCount: int


@runtime_checkable
class TenantRepository(Protocol):
    def create(self, tenant: Tenant) -> None: ...

    def update(self, tenant: Tenant) -> None: ...

    def getById(self, tenantId: uuid.UUID) -> Tenant | None: ...

    def getByCode(self, code: str) -> Tenant | None: ...

    def existsByCode(self, code: str) -> bool: ...

    def list(self, filters: TenantFilters) -> TenantPage: ...
