"""Identity repository contracts (§10) — every selector carries its tenant
scope (§10/BR-TEN-001: ``getById(userId, tenantId)``, never bare)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from apps.identity.domain.entities.session import Session
from apps.identity.domain.entities.tenantMembership import TenantMembership
from apps.identity.domain.entities.user import User
from apps.identity.domain.valueObjects.accessGrant import AccessGrant


@dataclass(frozen=True)
class UserFilters:
    tenantId: uuid.UUID
    status: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class UserPage:
    items: list[User]
    totalCount: int


@runtime_checkable
class UserRepository(Protocol):
    def create(self, user: User) -> None: ...

    def update(self, user: User) -> None: ...

    def getById(self, userId: uuid.UUID, tenantId: uuid.UUID | None = None) -> User | None:
        """Lookup; when ``tenantId`` is given the row must match it."""

    def getByUsername(self, tenantId: uuid.UUID, username: str) -> User | None: ...

    def existsByUsername(self, tenantId: uuid.UUID, username: str) -> bool: ...

    def existsByEmail(self, tenantId: uuid.UUID, email: str) -> bool: ...

    def list(self, filters: UserFilters) -> UserPage: ...


@runtime_checkable
class SessionRepository(Protocol):
    def create(self, session: Session) -> None: ...

    def update(self, session: Session) -> None: ...

    def findActiveByTokenHash(self, tokenHash: str) -> Session | None: ...


@runtime_checkable
class TenantMembershipRepository(Protocol):
    def create(self, membership: TenantMembership) -> None: ...

    def existsActive(self, userId: uuid.UUID, tenantId: uuid.UUID) -> bool: ...

    def activeTenantIdsOfUser(self, userId: uuid.UUID) -> list[uuid.UUID]: ...


@runtime_checkable
class AccessRepository(Protocol):
    """Grants read model for the evaluator (roles + direct permissions)."""

    def grantsOfUser(self, userId: uuid.UUID, tenantId: uuid.UUID) -> list[AccessGrant]: ...

    def ensureCatalogue(self, actions: list[tuple[str, str]]) -> None: ...

    def ensureRole(
        self,
        roleCode: str,
        roleName: str,
        actions: list[str],
        scopeType: str = "GLOBAL",
    ) -> uuid.UUID: ...

    def grantRoleToUser(
        self, userId: uuid.UUID, tenantId: uuid.UUID, roleId: uuid.UUID
    ) -> None: ...
