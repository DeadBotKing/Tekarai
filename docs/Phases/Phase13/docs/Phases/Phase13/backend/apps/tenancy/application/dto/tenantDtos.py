"""Tenant DTOs (Phase 06 §7) — plain data crossing layers, no logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TenantDto:
    id: str
    code: str
    name: str
    status: str
    createdAt: str


@dataclass(frozen=True)
class TenantPageDto:
    items: list[TenantDto] = field(default_factory=list)
    totalCount: int = 0
    page: int = 1
    pageSize: int = 50

    def asMeta(self) -> dict[str, Any]:
        return {
            "pagination": {
                "totalCount": self.totalCount,
                "page": self.page,
                "pageSize": self.pageSize,
                "totalPages": max(1, -(-self.totalCount // self.pageSize)),
                "hasNext": self.page * self.pageSize < self.totalCount,
                "hasPrevious": self.page > 1,
            }
        }


def tenantDtoFromDomain(tenant: Any) -> TenantDto:
    return TenantDto(
        id=str(tenant.id),
        code=str(tenant.code),
        name=tenant.name,
        status=str(tenant.status),
        createdAt=tenant.createdAt.isoformat(),
    )
