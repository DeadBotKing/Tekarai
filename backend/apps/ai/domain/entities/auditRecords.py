"""Pure audit and governance entities for Phase 13-O.

- ``AIAuditEntry`` — one append-only audit record (§28). Entity references
  (``requestId`` / ``attemptId`` / ``policyId``) are plain UUID columns
  with **no foreign keys** on purpose: retention purges of the referenced
  rows must never cascade into the audit trail, and purge order stays
  irrelevant. ``detail`` must already be scrubbed by the caller (the
  application layer scrubs; the entity only guards shape, never content).
- ``AIGovernancePolicy`` — one enforceable governance policy per tenant
  (§48): provider/model allowlists, disabled capabilities, the
  restricted-to-external boundary, and a daily cost budget.
- ``GovernanceRequest`` / ``GovernanceDecision`` / ``DecisionReason`` —
  the evaluation input/output values owned by the governance service.

The legacy ``AIAuditRecord`` entity (``aiRecords.py``) and the legacy
``aiAuditRecords`` table stay untouched; ledger convergence belongs to
sub-phase Z (contract §O.2.2).

The records contain no ORM, HTTP, provider SDK, Redis, queue, or Django
dependency. Persistence mapping belongs to the infrastructure layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.valueObjects.aiTypes import DATA_CLASSIFICATIONS, Money
from apps.ai.domain.valueObjects.auditTypes import (
    ensureActorType,
    ensureAuditAction,
    ensureAuditOutcome,
)
from apps.ai.domain.valueObjects.usageTypes import asUtc
from apps.sharedKernel.domain.errors import ValidationFailedError


def _normalizeCode(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalizeReference(value: Any) -> str:
    return str(value or "").strip()


def _ensureClassification(value: Any) -> str:
    normalized = _normalizeCode(value)
    if normalized not in DATA_CLASSIFICATIONS:
        raise ValidationFailedError(
            "Unknown data classification.", fieldErrors={"classification": normalized}
        )
    return normalized


def _ensureCodeList(values: Any, fieldName: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raise ValueError(f"Governance {fieldName} must be a list of codes.")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise ValueError(f"Governance {fieldName} must be a list of codes.") from exc
    normalized: list[str] = []
    for item in items:
        code = _normalizeCode(item)
        if not code:
            raise ValueError(f"Governance {fieldName} contains an empty code.")
        if code in normalized:
            raise ValueError(f"Governance {fieldName} contains duplicate code {code}.")
        normalized.append(code)
    return tuple(normalized)


def _normalizeContextSources(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        raise ValueError("Audit context sources must be a list of references.")
    try:
        items = tuple(values)
    except TypeError as exc:
        raise ValueError("Audit context sources must be a list of references.") from exc
    normalized: list[str] = []
    for item in items:
        reference = _normalizeReference(item)
        if not reference:
            raise ValueError("Audit context sources cannot hold empty references.")
        normalized.append(reference)
    return tuple(normalized)


def _normalizeDetail(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("Audit detail must be a mapping.")
    return {str(key): item for key, item in value.items()}


@dataclass
class AIAuditEntry:
    """One append-only audit record for a tenant.

    ``occurredAt`` is explicit domain time (not persistence time), so tests
    stay deterministic and backfilled decisions keep their true moment.
    ``prevHash``/``hash`` carry the tamper-evidence chain (§O.5); they are
    assigned by ``AuditTrailService`` (or rehydrated from the store), never
    by direct callers.
    """

    tenantId: uuid.UUID
    action: str
    occurredAt: datetime = field(default_factory=utcNow)
    id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    actorType: str = "SYSTEM"
    actorId: uuid.UUID | None = None
    requestId: uuid.UUID | None = None
    attemptId: uuid.UUID | None = None
    policyId: uuid.UUID | None = None
    capabilityCode: str = ""
    providerCode: str = ""
    modelCode: str = ""
    promptVersion: str = ""
    classification: str = "INTERNAL"
    outcome: str = "RECORDED"
    errorCode: str = ""
    correlationId: str = ""
    traceId: str = ""
    contextSources: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)
    prevHash: str = ""
    hash: str = ""

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.action = ensureAuditAction(self.action)
        self.occurredAt = asUtc(self.occurredAt)
        self.actorType = ensureActorType(self.actorType)
        if self.actorId is not None:
            self.actorId = requireUuid(self.actorId, "actorId")
        if self.requestId is not None:
            self.requestId = requireUuid(self.requestId, "requestId")
        if self.attemptId is not None:
            self.attemptId = requireUuid(self.attemptId, "attemptId")
        if self.policyId is not None:
            self.policyId = requireUuid(self.policyId, "policyId")
        self.capabilityCode = _normalizeCode(self.capabilityCode)
        self.providerCode = _normalizeCode(self.providerCode)
        self.modelCode = _normalizeCode(self.modelCode)
        self.promptVersion = _normalizeReference(self.promptVersion)
        self.classification = _ensureClassification(self.classification)
        self.outcome = ensureAuditOutcome(self.outcome)
        self.errorCode = _normalizeCode(self.errorCode)
        self.correlationId = _normalizeReference(self.correlationId)
        self.traceId = _normalizeReference(self.traceId)
        self.contextSources = _normalizeContextSources(self.contextSources)
        self.detail = _normalizeDetail(self.detail)
        self.prevHash = _normalizeReference(self.prevHash)
        self.hash = _normalizeReference(self.hash)


@dataclass
class AIGovernancePolicy:
    """One enforceable governance policy for a tenant (§48).

    Identity: ``tenantId`` alone — a tenant owns at most one policy, so
    governance evaluation never has to arbitrate between competing tenant
    policies. An empty ``allowedProviders``/``allowedModels`` list means
    "no allowlist restriction" (documented default-open); explicit
    restriction is expressed with ``disabledCapabilities`` (deny) and
    non-empty allowlists. ``maxCostPerDay`` of zero means unlimited.
    """

    tenantId: uuid.UUID
    id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    name: str = "default"
    allowedProviders: tuple[str, ...] = ()
    allowedModels: tuple[str, ...] = ()
    disabledCapabilities: tuple[str, ...] = ()
    allowRestrictedToExternal: bool = False
    maxCostPerDay: Decimal = field(default_factory=lambda: Decimal("0"))
    currency: str = "USD"
    description: str = ""
    isActive: bool = True
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.name = _normalizeReference(self.name)
        if not self.name:
            raise ValueError("Governance policy name is required.")
        self.allowedProviders = _ensureCodeList(self.allowedProviders, "allowedProviders")
        self.allowedModels = _ensureCodeList(self.allowedModels, "allowedModels")
        self.disabledCapabilities = _ensureCodeList(
            self.disabledCapabilities, "disabledCapabilities"
        )
        if not isinstance(self.allowRestrictedToExternal, bool):
            raise ValueError("Governance restricted-to-external flag must be boolean.")
        try:
            budget = Decimal(str(self.maxCostPerDay))
        except Exception as exc:
            raise ValueError("Governance daily budget is invalid.") from exc
        if budget < 0:
            raise ValueError("Governance daily budget cannot be negative.")
        self.maxCostPerDay = budget
        self.currency = _normalizeCode(self.currency)
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("Governance currency must be an ISO-4217 code.")
        self.description = _normalizeReference(self.description)
        self.createdAt = asUtc(self.createdAt)
        self.updatedAt = asUtc(self.updatedAt)

    def budget(self) -> Money:
        return Money(self.maxCostPerDay, self.currency)

    def deactivate(self, now: datetime | None = None) -> None:
        self.isActive = False
        self.updatedAt = asUtc(now) if now is not None else utcNow()

    def activate(self, now: datetime | None = None) -> None:
        self.isActive = True
        self.updatedAt = asUtc(now) if now is not None else utcNow()


@dataclass(frozen=True)
class GovernanceRequest:
    """One governance evaluation input (§O.7.2).

    ``providerIsExternal`` is asserted by the caller (the adapter registry
    knows which providers leave the platform); O never invents a taxonomy
    of provider types. ``daySpend``/``estimatedCost`` are optional: when the
    spend is unknown the budget rule is skipped (documented), never guessed.
    """

    tenantId: uuid.UUID
    capabilityCode: str = ""
    providerCode: str = ""
    modelCode: str = ""
    providerIsExternal: bool = False
    classification: str = "INTERNAL"
    estimatedCost: Money | None = None
    daySpend: Money | None = None
    actorType: str = "SYSTEM"
    actorId: uuid.UUID | None = None
    requestId: uuid.UUID | None = None
    correlationId: str = ""
    traceId: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        object.__setattr__(self, "capabilityCode", _normalizeCode(self.capabilityCode))
        object.__setattr__(self, "providerCode", _normalizeCode(self.providerCode))
        object.__setattr__(self, "modelCode", _normalizeCode(self.modelCode))
        if not isinstance(self.providerIsExternal, bool):
            raise ValueError("Governance provider visibility must be boolean.")
        object.__setattr__(self, "classification", _ensureClassification(self.classification))
        if self.estimatedCost is not None and not isinstance(self.estimatedCost, Money):
            raise ValueError("Governance estimated cost must be a Money value.")
        if self.daySpend is not None and not isinstance(self.daySpend, Money):
            raise ValueError("Governance day spend must be a Money value.")
        object.__setattr__(self, "actorType", ensureActorType(self.actorType))
        if self.actorId is not None:
            object.__setattr__(self, "actorId", requireUuid(self.actorId, "actorId"))
        if self.requestId is not None:
            object.__setattr__(self, "requestId", requireUuid(self.requestId, "requestId"))
        object.__setattr__(self, "correlationId", _normalizeReference(self.correlationId))
        object.__setattr__(self, "traceId", _normalizeReference(self.traceId))


@dataclass(frozen=True)
class DecisionReason:
    """One evaluated governance rule with its verdict and message."""

    rule: str
    allowed: bool
    message: str


@dataclass(frozen=True)
class GovernanceDecision:
    """ALLOW/DENY verdict with one reason per evaluated rule."""

    tenantId: uuid.UUID
    allowed: bool
    reasons: tuple[DecisionReason, ...]
    evaluatedAt: datetime


__all__ = [
    "AIAuditEntry",
    "AIGovernancePolicy",
    "DecisionReason",
    "GovernanceDecision",
    "GovernanceRequest",
]
