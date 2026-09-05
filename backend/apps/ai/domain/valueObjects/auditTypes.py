"""Framework-free audit and governance vocabularies for Phase 13-O.

This module defines the closed vocabularies used by the audit ledger and
the governance engine:

- ``AUDIT_ACTIONS`` — the 15 auditable actions. The first nine mirror the
  §36 platform events (``AIRequestCreated`` … ``AIFeedbackReceived``); the
  last six are owned by sub-phase O (governance decisions, policy
  administration, quota denials, retention purges). Lifecycle (G) and
  executor (M) phases log through ``logAudit``; O never invents new
  actions outside this tuple.
- ``ACTOR_TYPES`` — who performed the audited operation;
- ``AUDIT_OUTCOMES`` — the recorded result of the audited operation;
- ``SECRET_KEY_PATTERNS`` — case-insensitive key fragments whose values
  the audit scrubber always redacts (§47).

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
"""

from __future__ import annotations

from apps.sharedKernel.domain.errors import ValidationFailedError

AUDIT_ACTIONS = (
    "REQUEST_CREATED",
    "REQUEST_STARTED",
    "REQUEST_COMPLETED",
    "REQUEST_FAILED",
    "RESPONSE_GENERATED",
    "MODEL_CHANGED",
    "PROMPT_VERSION_ACTIVATED",
    "USAGE_RECORDED",
    "FEEDBACK_RECEIVED",
    "GOVERNANCE_ALLOW",
    "GOVERNANCE_DENY",
    "GOVERNANCE_POLICY_DEFINED",
    "GOVERNANCE_POLICY_UPDATED",
    "QUOTA_DENIED",
    "RETENTION_PURGED",
)
ACTOR_TYPES = (
    "USER",
    "SYSTEM",
    "SERVICE",
    "API_KEY",
)
AUDIT_OUTCOMES = (
    "RECORDED",
    "ALLOWED",
    "DENIED",
    "SUCCEEDED",
    "FAILED",
    "DEFINED",
    "UPDATED",
    "PURGED",
)

#: Exact chain-head marker for the first audit entry of a tenant (§O.5).
GENESIS_HASH = "GENESIS"

#: Placeholder stored instead of redacted secret values (§47).
REDACTED = "[REDACTED]"

#: Lowercase fragments; a mapping key containing any of them is scrubbed.
SECRET_KEY_PATTERNS = (
    "api_key",
    "apikey",
    "secret",
    "password",
    "passwd",
    "pwd",
    "access_token",
    "refresh_token",
    "auth_token",
    "id_token",
    "api_token",
    "bearer",
    "authorization",
    "private_key",
    "privatekey",
    "client_secret",
    "access_key",
    "accesskey",
    "session",
    "cookie",
    "credentials",
    "otp",
    "pin_code",
)


def ensureAuditAction(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in AUDIT_ACTIONS:
        raise ValidationFailedError("Unknown audit action.", fieldErrors={"action": normalized})
    return normalized


def ensureActorType(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in ACTOR_TYPES:
        raise ValidationFailedError(
            "Unknown audit actor type.", fieldErrors={"actorType": normalized}
        )
    return normalized


def ensureAuditOutcome(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in AUDIT_OUTCOMES:
        raise ValidationFailedError("Unknown audit outcome.", fieldErrors={"outcome": normalized})
    return normalized


def isSecretKey(key: str) -> bool:
    """Case-insensitive secret-key match.

    Fragment match against ``SECRET_KEY_PATTERNS``, plus the bare word
    ``token`` as a whole word or ``*_token`` suffix. A bare ``token``
    fragment is deliberately *not* matched: metering counters such as
    ``totalTokens`` must survive scrubbing (contract §O.6).
    """

    normalized = str(key or "").strip().lower()
    if any(fragment in normalized for fragment in SECRET_KEY_PATTERNS):
        return True
    return normalized == "token" or normalized.endswith("_token") or normalized.endswith("token")


__all__ = [
    "ACTOR_TYPES",
    "AUDIT_ACTIONS",
    "AUDIT_OUTCOMES",
    "GENESIS_HASH",
    "REDACTED",
    "SECRET_KEY_PATTERNS",
    "ensureActorType",
    "ensureAuditAction",
    "ensureAuditOutcome",
    "isSecretKey",
]
