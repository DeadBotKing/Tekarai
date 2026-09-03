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


@dataclass(frozen=True)
class ListSessionsQuery(Query):
    userId: str = ""  # own sessions (§9); another user requires audit.view


@dataclass(frozen=True)
class ListApiKeysQuery(Query):
    ownerType: str = "user"
    ownerId: str = ""


@dataclass(frozen=True)
class ListServiceAccountsQuery(Query):
    tenantId: str = ""


@dataclass(frozen=True)
class ListRolesQuery(Query):
    pass
