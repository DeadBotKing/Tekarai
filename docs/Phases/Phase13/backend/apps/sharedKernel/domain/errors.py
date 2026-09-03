"""Tekarai error architecture (Phase 06 §15).

One exception hierarchy shared by every layer; each error carries a stable
error code from ``docs/database/ErrorCodeCatalog.md`` and an advisory HTTP
status. The API layer maps these exceptions to the standard error envelope —
business code never shapes HTTP responses itself.

Layer taxonomy (Phase 06 §15):
- Domain errors          — DomainError, BusinessRuleViolationError
- Application errors     — UseCaseExecutionError, ConcurrencyConflictError
- Infrastructure errors  — ExternalServiceError
- Authentication errors  — AuthenticationRequiredError, InvalidCredentialsError,
                           TokenExpiredError
- Authorization errors   — PermissionDeniedError, TenantAccessDeniedError
- Not-found errors       — EntityNotFoundError
- Conflict errors        — ConflictError, DuplicateBusinessCodeError,
                           DuplicateActiveMembershipError
- Validation errors      — ValidationFailedError
"""

from __future__ import annotations


class TekaraiError(Exception):
    """Root of every deliberate Tekarai error (never leaked raw to clients)."""

    code: str = "SYS_INTERNAL_ERROR"
    httpStatus: int = 500

    def __init__(self, message: str = "", *, details: dict[str, object] | None = None) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details: dict[str, object] = details or {}


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


class ValidationFailedError(TekaraiError):
    """Domain/application validation refused the input (BR-DAT-014)."""

    code = "SYS_VALIDATION_FAILED"
    httpStatus = 422

    def __init__(
        self,
        message: str = "Validation failed.",
        *,
        fieldErrors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, details={"fields": fieldErrors or {}})
        self.fieldErrors = fieldErrors or {}


# --------------------------------------------------------------------------- #
# Domain / business rules
# --------------------------------------------------------------------------- #


class DomainError(TekaraiError):
    """Base class for invariant violations raised inside the domain layer."""

    code = "SYS_VALIDATION_FAILED"
    httpStatus = 422


class BusinessRuleViolationError(DomainError):
    """A catalogued business rule was violated (BusinessRuleCatalog IDs)."""

    code = "VAL_BUSINESS_RULE_VIOLATED"
    httpStatus = 422

    def __init__(self, message: str, *, ruleId: str) -> None:
        super().__init__(message, details={"ruleId": ruleId})
        self.ruleId = ruleId


class InvalidStateTransitionError(DomainError):
    """State-machine guard rejected the transition (StateMachineCatalog)."""

    code = "STATE_INVALID_TRANSITION"
    httpStatus = 409


# --------------------------------------------------------------------------- #
# Not found / conflict
# --------------------------------------------------------------------------- #


class EntityNotFoundError(TekaraiError):
    """Record absent, soft-deleted, or outside the caller's tenant.

    Deliberately indistinguishable across those causes so existence does not
    leak across tenant boundaries (ErrorCodeCatalog §core).
    """

    code = "SYS_RECORD_NOT_FOUND"
    httpStatus = 404

    def __init__(self, entityType: str, identifier: str = "") -> None:
        super().__init__(f"{entityType} not found.", details={"entityType": entityType})
        self.entityType = entityType
        self.identifier = identifier


class ConflictError(TekaraiError):
    """Generic conflicting-state failure."""

    code = "SYS_CONCURRENCY_CONFLICT"
    httpStatus = 409


class DuplicateBusinessCodeError(ConflictError):
    """UNIQUE(tenantId, businessKey) or global code uniqueness (§11)."""

    code = "DUP_BUSINESS_CODE"
    httpStatus = 409


class DuplicateActiveMembershipError(ConflictError):
    """One active membership per person per project/tenant (BR-PRJ-002)."""

    code = "DUP_ACTIVE_MEMBERSHIP"
    httpStatus = 409


class DuplicateIntegrationEventError(ConflictError):
    """Idempotency guard for external events (BR-INT-003)."""

    code = "DUP_INTEGRATION_EVENT"
    httpStatus = 409


class DuplicateIdentifierError(ConflictError):
    """A scoped identifier (username/email/serial) is taken (DUP_IDENTIFIER)."""

    code = "DUP_IDENTIFIER"
    httpStatus = 409


class CyclicReferenceError(DomainError):
    """Graph/dependency cycle rejected (BR-DAT-008)."""

    code = "VAL_CYCLIC_REFERENCE"
    httpStatus = 409


# --------------------------------------------------------------------------- #
# Authentication / authorization
# --------------------------------------------------------------------------- #


class AuthenticationRequiredError(TekaraiError):
    code = "AUTH_AUTHENTICATION_REQUIRED"
    httpStatus = 401


class InvalidCredentialsError(TekaraiError):
    code = "AUTH_CREDENTIALS_INVALID"
    httpStatus = 401


class TokenExpiredError(TekaraiError):
    code = "AUTH_TOKEN_EXPIRED"
    httpStatus = 401


class PermissionDeniedError(TekaraiError):
    """Server-side authorization refused the action (BR-SEC-002)."""

    code = "PERM_PERMISSION_DENIED"
    httpStatus = 403

    def __init__(self, message: str = "", *, action: str = "") -> None:
        super().__init__(message or "Permission denied.", details={"action": action})
        self.action = action


class TenantAccessDeniedError(PermissionDeniedError):
    """Cross-tenant access attempt (BR-TEN-001)."""

    code = "TENANT_ACCESS_DENIED"
    httpStatus = 403


class TenantSuspendedError(PermissionDeniedError):
    code = "TENANT_SUSPENDED"
    httpStatus = 403


# --------------------------------------------------------------------------- #
# Application / infrastructure
# --------------------------------------------------------------------------- #


class UseCaseExecutionError(TekaraiError):
    code = "SYS_INTERNAL_ERROR"
    httpStatus = 500


class ConcurrencyConflictError(TekaraiError):
    """Optimistic-lock version mismatch (BR-DAT-013)."""

    code = "SYS_CONCURRENCY_CONFLICT"
    httpStatus = 409


class RateLimitedError(TekaraiError):
    code = "SYS_RATE_LIMITED"
    httpStatus = 429

    def __init__(self, message: str = "Too many requests.", *, retryAfterSeconds: int = 60) -> None:
        super().__init__(message, details={"retryAfterSeconds": retryAfterSeconds})
        self.retryAfterSeconds = retryAfterSeconds


class ExternalServiceError(TekaraiError):
    """Outbound call to an external system failed (§39)."""

    code = "INT_EXECUTION_FAILED"
    httpStatus = 502
