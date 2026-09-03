"""Tenant queries (Phase 06 §6) — read-only intents."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Query


@dataclass(frozen=True)
class GetTenantQuery(Query):
    tenantId: str


@dataclass(frozen=True)
class ListTenantsQuery(Query):
    status: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50
