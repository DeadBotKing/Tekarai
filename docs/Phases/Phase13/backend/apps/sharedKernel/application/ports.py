"""Ports — the contracts infrastructure implements (Phase 06 §10).

Application code depends on these protocols only; the composition root
(config settings + apps.sharedKernel.infrastructure.wiring) binds concrete
implementations. Everything here is framework-free.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from apps.sharedKernel.domain.events import DomainEvent


@runtime_checkable
class Clock(Protocol):
    def nowUtc(self) -> datetime: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Transaction boundary lives in the application layer (§9).

    Use as a context manager; a failure rolls back every change of the use
    case, including audit writes made inside the same transaction (§9: if
    step 7 fails, everything rolls back).
    """

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, excType: object, excValue: object, traceback: object) -> None: ...


@runtime_checkable
class EventDispatcher(Protocol):
    """Publishes domain events after the transaction commits (§36)."""

    def dispatch(self, event: DomainEvent) -> None: ...


@runtime_checkable
class AuditRecorder(Protocol):
    """Append-only audit trail (Phase 06 §19 field list)."""

    def record(
        self,
        *,
        action: str,
        resourceType: str,
        resourceId: str,
        tenantId: uuid.UUID | None,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
    ) -> None: ...


@runtime_checkable
class TokenIssuer(Protocol):
    """Phase 07 §7 — issues short-lived JWT access tokens and MFA challenge
    tokens. Claims stay minimal (§8); permissions never ride in the token."""

    def issueAccessToken(
        self, *, userId: uuid.UUID, tenantId: uuid.UUID, sessionId: uuid.UUID
    ) -> tuple[str, int]: ...

    def issueMfaChallenge(
        self, *, userId: uuid.UUID, tenantId: uuid.UUID, sessionId: uuid.UUID
    ) -> str: ...

    def verifyAccessToken(self, token: str) -> dict: ...

    def verifyMfaChallenge(self, token: str) -> dict: ...


@runtime_checkable
class SecretVault(Protocol):
    """Phase 07 — protects at-rest secrets (TOTP secrets) so raw secrets
    never land in the database or logs (§41 DoD)."""

    def protect(self, raw: str) -> str: ...

    def reveal(self, protected: str) -> str: ...


@runtime_checkable
class PermissionGate(Protocol):
    """Server-side authorization decision (§17, six layers §44).

    ``actorId``/``tenantId`` come from the request context; ``action`` is an
    action-based code (BR-PER-001); ``targetTenantId``/``targetId`` enable
    object-level checks.
    """

    def hasPermission(
        self,
        actorId: uuid.UUID,
        action: str,
        *,
        tenantId: uuid.UUID | None = None,
        targetTenantId: uuid.UUID | None = None,
        targetId: uuid.UUID | None = None,
    ) -> bool: ...


@runtime_checkable
class SessionPrincipal(Protocol):
    """What authentication resolves a bearer token into (§16)."""

    userId: uuid.UUID
    tenantId: uuid.UUID
    displayName: str


@runtime_checkable
class SessionVerifier(Protocol):
    """Authentication port: token → principal. Raises on invalid/expired."""

    def verifyToken(self, token: str) -> SessionPrincipal: ...


@runtime_checkable
class IdempotencyStore(Protocol):
    """Stores the fingerprint → response mapping (Phase 06 §20)."""

    def lookup(self, key: str) -> tuple[int, dict[str, object]] | None: ...

    def store(
        self, key: str, httpStatus: int, body: dict[str, object], ttlSeconds: int
    ) -> None: ...


@runtime_checkable
class RateLimiter(Protocol):
    """Fixed-window counter (§23). Returns the current hit count."""

    def hit(self, scope: str, identity: str, limit: int, windowSeconds: int) -> int:
        """Register a hit and report the count inside the window."""
        ...
