"""Identity queries (§6)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Query


@dataclass(frozen=True)
class GetUserQuery(Query):
    userId: str


@dataclass(frozen=True)
class ListUsersQuery(Query):
    status: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50
    tenantId: str = ""  # optional override — only honoured for GLOBAL grants


@dataclass(frozen=True)
class GetCurrentAccountQuery(Query):
    pass  # actor comes from the request context (§25)
