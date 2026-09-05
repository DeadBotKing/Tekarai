"""Pure metering and quota entities for Phase 13-N.

- ``AIUsageAttempt`` — one provider attempt (a request may own several
  attempts once sub-phase M adds retry/fallback; N records them
  independently so M integrates without a schema change);
- ``AIQuotaPolicy`` — one enforceable limit on a (scope, dimension, window)
  axis with deterministic window arithmetic;
- ``AIQuotaCounter`` — the consumed amounts of one policy inside one window.

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
from apps.ai.domain.valueObjects.aiTypes import CostRate, Money, TokenUsage
from apps.ai.domain.valueObjects.usageTypes import (
    UsageAttribution,
    asUtc,
    ensureAttemptOutcome,
    ensureQuotaDimension,
    ensureQuotaScope,
    ensureQuotaWindow,
    windowStart,
)


def _normalizeReference(value: Any) -> str:
    return str(value or "").strip()


def _normalizeTokenLimit(value: Any, fieldName: str) -> Decimal:
    try:
        normalized = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"Quota limit for {fieldName} is invalid.") from exc
    if normalized <= 0:
        raise ValueError(f"Quota limit for {fieldName} must be positive.")
    return normalized


@dataclass
class AIUsageAttempt:
    """One metered provider attempt inside an AI request.

    ``attemptNumber`` is 1-based per request. Failed attempts are recorded
    with the same shape as succeeded ones: providers bill failed calls, so
    quota consumption is outcome-agnostic (contract §N.4).
    """

    tenantId: uuid.UUID
    requestId: uuid.UUID
    providerId: uuid.UUID
    modelId: uuid.UUID
    providerCode: str
    modelCode: str
    usage: TokenUsage
    latencyMs: int = 0
    queueTimeMs: int = 0
    contextBuildTimeMs: int = 0
    providerTimeMs: int = 0
    validationTimeMs: int = 0
    id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    operationId: uuid.UUID | None = None
    attemptNumber: int = 1
    capabilityCode: str = ""
    requestedBy: uuid.UUID | None = None
    costAmount: Decimal = field(default_factory=lambda: Decimal("0"))
    costCurrency: str = "USD"
    outcome: str = "SUCCEEDED"
    errorCode: str = ""
    idempotencyKey: str = ""
    correlationId: str = ""
    traceId: str = ""
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.providerId = requireUuid(self.providerId, "providerId")
        self.modelId = requireUuid(self.modelId, "modelId")
        self.id = requireUuid(self.id, "id")
        if self.operationId is not None:
            self.operationId = requireUuid(self.operationId, "operationId")
        if self.requestedBy is not None:
            self.requestedBy = requireUuid(self.requestedBy, "requestedBy")
        if not isinstance(self.attemptNumber, int) or isinstance(self.attemptNumber, bool):
            raise ValueError("Attempt number must be an integer.")
        if self.attemptNumber < 1:
            raise ValueError("Attempt number is 1-based.")
        self.providerCode = _normalizeReference(self.providerCode).upper()
        self.modelCode = _normalizeReference(self.modelCode).upper()
        self.capabilityCode = _normalizeReference(self.capabilityCode).upper()
        if not self.providerCode or not self.modelCode:
            raise ValueError("Attempt provider and model codes are required.")
        if not isinstance(self.usage, TokenUsage):
            raise ValueError("Attempt usage must be a TokenUsage value object.")
        timings = (
            self.latencyMs,
            self.queueTimeMs,
            self.contextBuildTimeMs,
            self.providerTimeMs,
            self.validationTimeMs,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in timings
        ):
            raise ValueError("Attempt timings cannot be negative.")
        self.costAmount = Decimal(str(self.costAmount))
        self.costCurrency = _normalizeReference(self.costCurrency).upper()
        if self.costAmount < 0 or len(self.costCurrency) != 3 or not self.costCurrency.isalpha():
            raise ValueError("Attempt cost amount/currency is invalid.")
        self.outcome = ensureAttemptOutcome(self.outcome)
        self.errorCode = _normalizeReference(self.errorCode).upper()
        self.idempotencyKey = _normalizeReference(self.idempotencyKey)
        self.correlationId = _normalizeReference(self.correlationId)
        self.traceId = _normalizeReference(self.traceId)
        self.createdAt = asUtc(self.createdAt)

    @property
    def totalTokens(self) -> int:
        return self.usage.totalTokens

    @property
    def totalTimeMs(self) -> int:
        parts = (
            self.queueTimeMs + self.contextBuildTimeMs + self.providerTimeMs + self.validationTimeMs
        )
        return self.latencyMs or parts

    def cost(self) -> Money:
        return Money(self.costAmount, self.costCurrency)

    def attribution(self) -> UsageAttribution:
        return UsageAttribution(
            capabilityCode=self.capabilityCode,
            modelCode=self.modelCode,
            providerCode=self.providerCode,
            userId=str(self.requestedBy) if self.requestedBy else "",
        )


@dataclass
class AIQuotaPolicy:
    """One enforceable quota limit for a tenant.

    Identity: (tenantId, scope, scopeReference, dimension, window).
    ``scopeReference`` semantics per scope: TENANT → empty; USER → user UUID;
    DEPARTMENT → department code; PROJECT → project id; CAPABILITY →
    capability code; MODEL → model code. Only COST-dimension policies carry
    a meaningful currency.
    """

    tenantId: uuid.UUID
    scope: str
    scopeReference: str
    dimension: str
    window: str
    limitValue: Decimal
    id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    currency: str = "USD"
    description: str = ""
    isActive: bool = True
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.scope = ensureQuotaScope(self.scope)
        self.scopeReference = _normalizeReference(self.scopeReference).upper()
        self.dimension = ensureQuotaDimension(self.dimension)
        self.window = ensureQuotaWindow(self.window)
        if self.scope == "TENANT" and self.scopeReference:
            raise ValueError("Tenant-scope quota policies carry no reference.")
        if self.scope != "TENANT" and not self.scopeReference:
            raise ValueError(f"Quota scope {self.scope} requires a reference.")
        self.limitValue = _normalizeTokenLimit(self.limitValue, self.dimension)
        if self.dimension != "COST" and self.limitValue != int(self.limitValue):
            raise ValueError("Non-cost quota limits must be whole numbers.")
        self.currency = _normalizeReference(self.currency).upper()
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("Quota currency must be an ISO-4217 code.")
        self.description = _normalizeReference(self.description)
        self.createdAt = asUtc(self.createdAt)
        self.updatedAt = asUtc(self.updatedAt)

    def limit(self) -> Decimal | int:
        if self.dimension == "COST":
            return self.limitValue
        return int(self.limitValue)

    def windowStartFor(self, moment: datetime) -> datetime:
        return windowStart(moment, self.window)

    def matches(self, attribution: UsageAttribution) -> bool:
        if not isinstance(attribution, UsageAttribution):
            raise ValueError("Quota matching requires a UsageAttribution.")
        if self.scope == "TENANT":
            return True
        if self.scope == "USER":
            return bool(attribution.userId) and attribution.userId.upper() == self.scopeReference
        if self.scope == "DEPARTMENT":
            return (
                bool(attribution.departmentCode)
                and attribution.departmentCode == self.scopeReference
            )
        if self.scope == "PROJECT":
            return (
                bool(attribution.projectId) and attribution.projectId.upper() == self.scopeReference
            )
        if self.scope == "CAPABILITY":
            return (
                bool(attribution.capabilityCode)
                and attribution.capabilityCode == self.scopeReference
            )
        return bool(attribution.modelCode) and attribution.modelCode == self.scopeReference

    def deactivate(self, now: datetime | None = None) -> None:
        self.isActive = False
        self.updatedAt = asUtc(now) if now is not None else utcNow()

    def activate(self, now: datetime | None = None) -> None:
        self.isActive = True
        self.updatedAt = asUtc(now) if now is not None else utcNow()


@dataclass
class AIQuotaCounter:
    """Consumed amounts of one policy inside one window.

    Counters are append-only within their window: consumption only grows.
    A new window starts a new counter row; old rows remain readable for
    reporting until the retention policy of sub-phase O removes them.
    """

    tenantId: uuid.UUID
    policyId: uuid.UUID
    windowStart: datetime
    id: uuid.UUID = field(default_factory=lambda: uuid.uuid4())
    consumedRequests: int = 0
    consumedInputTokens: int = 0
    consumedOutputTokens: int = 0
    consumedCost: Decimal = field(default_factory=lambda: Decimal("0"))
    currency: str = "USD"
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.policyId = requireUuid(self.policyId, "policyId")
        self.id = requireUuid(self.id, "id")
        self.windowStart = asUtc(self.windowStart)
        counters = (self.consumedRequests, self.consumedInputTokens, self.consumedOutputTokens)
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in counters
        ):
            raise ValueError("Quota counters cannot be negative.")
        self.consumedCost = Decimal(str(self.consumedCost))
        self.currency = _normalizeReference(self.currency).upper()
        if self.consumedCost < 0 or len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("Quota cost counter is invalid.")
        self.updatedAt = asUtc(self.updatedAt)

    @property
    def consumedTotalTokens(self) -> int:
        return self.consumedInputTokens + self.consumedOutputTokens

    def consumedFor(self, dimension: str) -> Decimal | int:
        normalized = ensureQuotaDimension(dimension)
        if normalized == "REQUESTS":
            return self.consumedRequests
        if normalized == "INPUT_TOKENS":
            return self.consumedInputTokens
        if normalized == "OUTPUT_TOKENS":
            return self.consumedOutputTokens
        if normalized == "TOTAL_TOKENS":
            return self.consumedTotalTokens
        return self.consumedCost

    def addConsumption(
        self,
        usage: TokenUsage,
        cost: Money,
        *,
        now: datetime | None = None,
    ) -> AIQuotaCounter:
        if not isinstance(usage, TokenUsage) or not isinstance(cost, Money):
            raise ValueError("Quota consumption requires TokenUsage and Money values.")
        if cost.currency != self.currency:
            raise ValueError("Quota consumption currency must match the counter currency.")
        self.consumedRequests += 1
        self.consumedInputTokens += usage.inputTokens
        self.consumedOutputTokens += usage.outputTokens
        self.consumedCost += cost.amount
        self.updatedAt = asUtc(now) if now is not None else utcNow()
        return self

    def remainingFor(self, policy: AIQuotaPolicy) -> Decimal | int:
        if not isinstance(policy, AIQuotaPolicy):
            raise ValueError("Remaining quota requires an AIQuotaPolicy.")
        if policy.id != self.policyId:
            raise ValueError("Counter does not belong to the given policy.")
        if policy.dimension == "COST" and policy.currency != self.currency:
            raise ValueError("Counter currency must match the policy currency.")
        limit = policy.limit()
        consumed = self.consumedFor(policy.dimension)
        remaining = Decimal(str(limit)) - Decimal(str(consumed))
        if remaining < 0:
            remaining = Decimal("0")
        return remaining if policy.dimension == "COST" else int(remaining)

    def isExhaustedBy(self, policy: AIQuotaPolicy, usage: TokenUsage, cost: Money) -> bool:
        if not isinstance(policy, AIQuotaPolicy):
            raise ValueError("Exhaustion check requires an AIQuotaPolicy.")
        if policy.id != self.policyId:
            raise ValueError("Counter does not belong to the given policy.")
        if policy.dimension == "COST" and (
            policy.currency != self.currency or cost.currency != self.currency
        ):
            raise ValueError("Cost exhaustion check requires matching currencies.")
        limit = Decimal(str(policy.limit()))
        if policy.dimension == "REQUESTS":
            projected = Decimal(self.consumedRequests + 1)
        elif policy.dimension == "INPUT_TOKENS":
            projected = Decimal(self.consumedInputTokens + usage.inputTokens)
        elif policy.dimension == "OUTPUT_TOKENS":
            projected = Decimal(self.consumedOutputTokens + usage.outputTokens)
        elif policy.dimension == "TOTAL_TOKENS":
            projected = Decimal(self.consumedTotalTokens + usage.totalTokens)
        else:
            projected = self.consumedCost + cost.amount
        return projected > limit


def costForAttempt(usage: TokenUsage, rate: CostRate) -> Money:
    """Calculate the money cost of one attempt from model rates (§26)."""

    if not isinstance(usage, TokenUsage) or not isinstance(rate, CostRate):
        raise ValueError("Cost calculation requires TokenUsage and CostRate values.")
    return rate.calculate(usage)


__all__ = [
    "AIQuotaCounter",
    "AIQuotaPolicy",
    "AIUsageAttempt",
    "costForAttempt",
]
