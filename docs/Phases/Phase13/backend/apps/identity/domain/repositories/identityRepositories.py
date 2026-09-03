"""Identity repository contracts (Phase 07 §29 domain model).

Every selector carries its tenant scope (BR-TEN-001). Contracts are
Protocols implemented by infrastructure with the ORM.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from apps.identity.domain.entities.apiKey import ApiKey
from apps.identity.domain.entities.credential import (
    PasswordHistoryEntry,
    PasswordResetToken,
    VerificationToken,
)
from apps.identity.domain.entities.mfa import MfaFactor
from apps.identity.domain.entities.serviceAccount import ServiceAccount
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

    def update(self, user: User) -> None:
        """Persist the full aggregate incl. security bookkeeping (§4)."""

    def getById(self, userId: uuid.UUID, tenantId: uuid.UUID | None = None) -> User | None: ...

    def getByIdentifier(self, tenantId: uuid.UUID, identifier: str) -> User | None:
        """Login-identifier resolution (§4): username OR email — extensible."""

    def getByUsername(self, tenantId: uuid.UUID, username: str) -> User | None: ...

    def existsByUsername(self, tenantId: uuid.UUID, username: str) -> bool: ...

    def existsByEmail(self, tenantId: uuid.UUID, email: str) -> bool: ...

    def list(self, filters: UserFilters) -> UserPage: ...


@runtime_checkable
class SessionRepository(Protocol):
    def create(self, session: Session) -> None: ...

    def update(self, session: Session) -> None: ...

    def getById(self, sessionId: uuid.UUID) -> Session | None: ...

    def findActiveByRefreshHash(self, refreshTokenHash: str) -> Session | None: ...

    def listActiveForUser(self, userId: uuid.UUID) -> list[Session]: ...

    def revokeAllForUser(self, userId: uuid.UUID, now: datetime) -> int: ...


@runtime_checkable
class TenantMembershipRepository(Protocol):
    def create(self, membership: TenantMembership) -> None: ...

    def update(self, membership: TenantMembership) -> None: ...

    def get(self, userId: uuid.UUID, tenantId: uuid.UUID) -> TenantMembership | None: ...

    def existsActive(self, userId: uuid.UUID, tenantId: uuid.UUID) -> bool: ...

    def listForUser(self, userId: uuid.UUID) -> list[TenantMembership]: ...

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

    def revokeRoleFromUser(self, userId: uuid.UUID, roleId: uuid.UUID) -> None: ...


@dataclass(frozen=True)
class RoleSummary:
    """Read model for role administration (no ORM types cross the border)."""

    id: uuid.UUID
    code: str
    name: str
    scopeType: str
    actions: list[str]


@runtime_checkable
class RoleRepository(Protocol):
    def create(self, code: str, name: str, scopeType: str, actions: list[str]) -> uuid.UUID: ...

    def update(self, roleId: uuid.UUID, *, name: str | None, actions: list[str] | None) -> None: ...

    def delete(self, roleId: uuid.UUID) -> None: ...

    def getById(self, roleId: uuid.UUID) -> RoleSummary | None: ...

    def list(self) -> list[RoleSummary]: ...


@runtime_checkable
class CredentialRepository(Protocol):
    def addPasswordHistory(self, entry: PasswordHistoryEntry) -> None: ...

    def passwordHistoryOf(self, userId: uuid.UUID, limit: int = 5) -> list[str]: ...

    def saveVerificationToken(self, token: VerificationToken) -> None: ...

    def findVerificationToken(self, tokenHash: str) -> VerificationToken | None: ...

    def markVerificationTokenVerified(self, tokenId: uuid.UUID) -> None: ...

    def registerVerificationAttempt(self, tokenId: uuid.UUID) -> None: ...

    def saveResetToken(self, token: PasswordResetToken) -> None: ...

    def findResetToken(self, tokenHash: str) -> PasswordResetToken | None: ...

    def markResetTokenUsed(self, tokenId: uuid.UUID) -> None: ...


@runtime_checkable
class ApiKeyRepository(Protocol):
    def create(self, apiKey: ApiKey) -> None: ...

    def revoke(self, apiKeyId: uuid.UUID, now: datetime) -> None: ...

    def findByKeyHash(self, keyHash: str) -> ApiKey | None: ...

    def getById(self, apiKeyId: uuid.UUID) -> ApiKey | None: ...

    def listForOwner(self, ownerType: str, ownerId: uuid.UUID) -> list[ApiKey]: ...

    def markUsed(self, apiKeyId: uuid.UUID, now: datetime) -> None: ...


@runtime_checkable
class ServiceAccountRepository(Protocol):
    def create(self, account: ServiceAccount) -> None: ...

    def update(self, account: ServiceAccount) -> None: ...

    def getById(self, accountId: uuid.UUID) -> ServiceAccount | None: ...

    def existsByCode(self, tenantId: uuid.UUID, code: str) -> bool: ...

    def list(self, tenantId: uuid.UUID) -> list[ServiceAccount]: ...


@runtime_checkable
class MfaRepository(Protocol):
    def save(self, factor: MfaFactor) -> None: ...

    def getById(self, factorId: uuid.UUID) -> MfaFactor | None: ...

    def activeFactorOf(self, userId: uuid.UUID) -> MfaFactor | None: ...

    def saveRecoveryCodes(self, userId: uuid.UUID, codeHashes: list[str]) -> None: ...

    def consumeRecoveryCode(self, userId: uuid.UUID, codeHash: str) -> bool: ...


@runtime_checkable
class SecurityEventRecorder(Protocol):
    """Security events (§27/§38) — aligned with, written beside, the audit."""

    def record(
        self,
        eventType: str,
        *,
        userId: uuid.UUID | None = None,
        tenantId: uuid.UUID | None = None,
        sessionId: uuid.UUID | None = None,
        result: str = "success",
        reason: str = "",
    ) -> None: ...
