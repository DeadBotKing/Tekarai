"""Pure usage metering, cost accounting and latency statistics (Phase 13-N).

``UsageMeteringService`` is a tenant-scoped in-memory coordinator for
per-attempt usage records (§26), §27 latency splits and §34 aggregates. It
is deliberately not a repository: state disappears with the process and an
application adapter maps successful recordings to its own persistence
boundary (the same split as the Phase 13-G lifecycle service).

``CostCalculator`` prices token usage from model ``CostRate`` values and
enforces per-request cost caps without knowing any provider.

``AIUsageRecorded`` is the §36 domain event carrier. Publishing it to the
Tekarai event bus is a later concern (sub-phases O/P); the carrier keeps
the bus binding free of content and secrets by construction.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.usageRecords import AIUsageAttempt, costForAttempt
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AICostLimitExceeded,
    AIIdempotencyConflict,
    AIUsageAttemptAlreadyRegistered,
    AIUsageAttemptNotFound,
)
from apps.ai.domain.valueObjects.aiTypes import CostRate, Money, TokenUsage
from apps.ai.domain.valueObjects.usageTypes import (
    asUtc,
    ensureAttemptOutcome,
)


def _stableValue(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _stableValue(value[key]) for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_stableValue(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_stableValue(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, (uuid.UUID, datetime, Decimal)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _attemptFingerprint(
    *,
    tenantId: uuid.UUID,
    requestId: uuid.UUID,
    attemptNumber: int,
    providerId: uuid.UUID,
    modelId: uuid.UUID,
    usage: TokenUsage,
    costAmount: Decimal,
    costCurrency: str,
    outcome: str,
) -> str:
    identity = {
        "tenantId": str(tenantId),
        "requestId": str(requestId),
        "attemptNumber": attemptNumber,
        "providerId": str(providerId),
        "modelId": str(modelId),
        "inputTokens": usage.inputTokens,
        "outputTokens": usage.outputTokens,
        "costAmount": str(costAmount),
        "costCurrency": costCurrency,
        "outcome": outcome,
    }
    encoded = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AttemptDescriptor:
    """Safe attempt read model; carries counts and codes, never content."""

    tenantId: uuid.UUID
    attemptId: uuid.UUID
    requestId: uuid.UUID
    operationId: uuid.UUID | None
    attemptNumber: int
    providerCode: str
    modelCode: str
    capabilityCode: str
    inputTokens: int
    outputTokens: int
    totalTokens: int
    costAmount: Decimal
    costCurrency: str
    queueTimeMs: int
    contextBuildTimeMs: int
    providerTimeMs: int
    validationTimeMs: int
    totalTimeMs: int
    outcome: str
    errorCode: str
    correlationId: str
    traceId: str
    createdAt: datetime


@dataclass(frozen=True)
class LatencyStats:
    """§34 latency aggregate over a set of attempt totals (milliseconds)."""

    count: int
    totalMs: int
    averageMs: int
    p95Ms: int
    maxMs: int


@dataclass(frozen=True)
class RequestUsageRollup:
    """Per-request totals derived from that request's attempts."""

    tenantId: uuid.UUID
    requestId: uuid.UUID
    attempts: int
    succeeded: int
    failed: int
    inputTokens: int
    outputTokens: int
    totalTokens: int
    costAmount: Decimal
    costCurrency: str
    totalTimeMs: int


@dataclass(frozen=True)
class UsageBreakdown:
    key: str
    requests: int
    inputTokens: int
    outputTokens: int
    totalTokens: int
    costAmount: Decimal


@dataclass(frozen=True)
class UsageSummary:
    """§26 reportable aggregate for one tenant with an optional filter."""

    tenantId: uuid.UUID
    attempts: int
    succeeded: int
    failed: int
    inputTokens: int
    outputTokens: int
    totalTokens: int
    costAmount: Decimal
    costCurrency: str
    latency: LatencyStats
    byCapability: tuple[UsageBreakdown, ...] = ()
    byModel: tuple[UsageBreakdown, ...] = ()
    byProvider: tuple[UsageBreakdown, ...] = ()


@dataclass(frozen=True)
class AIUsageRecorded:
    """§36 domain event carrier for one recorded attempt.

    The carrier intentionally contains no prompt, completion, context, or
    secret — only identifiers, counts, money, and timings.
    """

    tenantId: uuid.UUID
    attemptId: uuid.UUID
    requestId: uuid.UUID
    operationId: uuid.UUID | None
    providerCode: str
    modelCode: str
    capabilityCode: str
    inputTokens: int
    outputTokens: int
    totalTokens: int
    costAmount: Decimal
    costCurrency: str
    totalTimeMs: int
    outcome: str
    correlationId: str
    traceId: str
    recordedAt: datetime


class CostCalculator:
    """Pure cost arithmetic over token usage and model rates."""

    @staticmethod
    def calculate(usage: TokenUsage, rate: CostRate) -> Money:
        return costForAttempt(usage, rate)

    @staticmethod
    def total(costs: Iterable[Money]) -> Money:
        items = list(costs)
        if not items:
            return Money(Decimal("0"), "USD")
        currencies = {item.currency for item in items}
        if len(currencies) != 1:
            raise AIConfigurationError("Usage cost totals require a single currency.")
        amount = sum((item.amount for item in items), Decimal("0"))
        return Money(amount, items[0].currency)

    @staticmethod
    def assertWithinLimit(cost: Money, limit: Money) -> Money:
        if not isinstance(cost, Money) or not isinstance(limit, Money):
            raise AIConfigurationError("Cost limit checks require Money values.")
        if cost.currency != limit.currency:
            raise AIConfigurationError("Cost and cost limit currencies must match.")
        if cost.amount > limit.amount:
            raise AICostLimitExceeded(f"AI cost {cost.amount} exceeds the {limit.amount} limit.")
        return cost


def attemptFingerprint(attempt: AIUsageAttempt) -> str:
    """Stable tenant-scoped identity of an attempt for idempotent stores."""

    if not isinstance(attempt, AIUsageAttempt):
        raise ValueError("Fingerprint requires an AIUsageAttempt.")
    return _attemptFingerprint(
        tenantId=attempt.tenantId,
        requestId=attempt.requestId,
        attemptNumber=attempt.attemptNumber,
        providerId=attempt.providerId,
        modelId=attempt.modelId,
        usage=attempt.usage,
        costAmount=attempt.costAmount,
        costCurrency=attempt.costCurrency,
        outcome=attempt.outcome,
    )


def latencyStatistics(totals: Iterable[int]) -> LatencyStats:
    """Nearest-rank p95 over attempt total times (§34 latencyAverage/latencyP95)."""

    samples = sorted(int(value) for value in totals)
    if not samples:
        return LatencyStats(count=0, totalMs=0, averageMs=0, p95Ms=0, maxMs=0)
    if any(value < 0 for value in samples):
        raise ValueError("Latency samples cannot be negative.")
    total = sum(samples)
    rank = max(1, math.ceil(0.95 * len(samples)))
    return LatencyStats(
        count=len(samples),
        totalMs=total,
        averageMs=total // len(samples),
        p95Ms=samples[rank - 1],
        maxMs=samples[-1],
    )


class UsageMeteringService:
    """Tenant-scoped in-memory coordinator for attempt usage records.

    Recordings are idempotent per tenant-scoped ``idempotencyKey``: repeating
    the same key with the same fingerprint returns the stored attempt, while
    a reused key with a different fingerprint raises ``AIIdempotencyConflict``
    (the same contract as the Phase 13-G lifecycle service).
    """

    def __init__(self, *, now: Any = utcNow) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._now = now
        self._attempts: dict[tuple[uuid.UUID, uuid.UUID], AIUsageAttempt] = {}
        self._byRequest: dict[tuple[uuid.UUID, uuid.UUID], list[uuid.UUID]] = {}
        self._idempotency: dict[tuple[uuid.UUID, str], tuple[str, uuid.UUID]] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def recordAttempt(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        providerId: uuid.UUID | str,
        modelId: uuid.UUID | str,
        *,
        providerCode: str,
        modelCode: str,
        inputTokens: int,
        outputTokens: int,
        costAmount: Decimal | int | str = Decimal("0"),
        costCurrency: str = "USD",
        queueTimeMs: int = 0,
        contextBuildTimeMs: int = 0,
        providerTimeMs: int = 0,
        validationTimeMs: int = 0,
        latencyMs: int = 0,
        attemptNumber: int = 1,
        operationId: uuid.UUID | str | None = None,
        capabilityCode: str = "",
        requestedBy: uuid.UUID | str | None = None,
        outcome: str = "SUCCEEDED",
        errorCode: str = "",
        idempotencyKey: str = "",
        correlationId: str = "",
        traceId: str = "",
        attemptId: uuid.UUID | str | None = None,
    ) -> AIUsageAttempt:
        tenant = requireUuid(tenantId, "tenantId")
        request = requireUuid(requestId, "requestId")
        provider = requireUuid(providerId, "providerId")
        model = requireUuid(modelId, "modelId")
        normalizedOutcome = ensureAttemptOutcome(outcome)
        usage = TokenUsage(inputTokens=inputTokens, outputTokens=outputTokens)
        normalizedCost = Decimal(str(costAmount))
        normalizedKey = str(idempotencyKey or "").strip()
        if not normalizedKey and self._duplicateAttemptNumber(tenant, request, attemptNumber):
            raise AIUsageAttemptAlreadyRegistered(str(request))
        fingerprint = _attemptFingerprint(
            tenantId=tenant,
            requestId=request,
            attemptNumber=attemptNumber,
            providerId=provider,
            modelId=model,
            usage=usage,
            costAmount=normalizedCost,
            costCurrency=str(costCurrency or "").strip().upper(),
            outcome=normalizedOutcome,
        )
        if normalizedKey:
            idempotencySlot = (tenant, normalizedKey)
            previous = self._idempotency.get(idempotencySlot)
            if previous is not None:
                previousFingerprint, previousAttemptId = previous
                if previousFingerprint == fingerprint:
                    return self._attempts[(tenant, previousAttemptId)]
                raise AIIdempotencyConflict(
                    "The tenant-scoped usage idempotency key is already bound to another attempt."
                )
        attempt = AIUsageAttempt(
            tenantId=tenant,
            requestId=request,
            providerId=provider,
            modelId=model,
            providerCode=providerCode,
            modelCode=modelCode,
            usage=usage,
            latencyMs=latencyMs,
            queueTimeMs=queueTimeMs,
            contextBuildTimeMs=contextBuildTimeMs,
            providerTimeMs=providerTimeMs,
            validationTimeMs=validationTimeMs,
            id=requireUuid(attemptId, "attemptId") if attemptId is not None else uuid.uuid4(),
            operationId=requireUuid(operationId, "operationId")
            if operationId is not None
            else None,
            attemptNumber=attemptNumber,
            capabilityCode=capabilityCode,
            requestedBy=requireUuid(requestedBy, "requestedBy")
            if requestedBy is not None
            else None,
            costAmount=normalizedCost,
            costCurrency=costCurrency,
            outcome=normalizedOutcome,
            errorCode=errorCode,
            idempotencyKey=normalizedKey,
            correlationId=correlationId,
            traceId=traceId,
            createdAt=self._now(),
        )
        attemptKey = (tenant, attempt.id)
        if attemptKey in self._attempts:
            raise AIUsageAttemptAlreadyRegistered(str(attempt.id))
        self._attempts[attemptKey] = attempt
        self._byRequest.setdefault((tenant, request), []).append(attempt.id)
        if normalizedKey:
            self._idempotency[(tenant, normalizedKey)] = (fingerprint, attempt.id)
        return attempt

    def importAttempt(self, attempt: AIUsageAttempt) -> AIUsageAttempt:
        """Load a persisted attempt (application hydration) without re-validating business rules."""

        if not isinstance(attempt, AIUsageAttempt):
            raise ValueError("Only AIUsageAttempt records can be imported.")
        key = (attempt.tenantId, attempt.id)
        if key in self._attempts:
            return self._attempts[key]
        self._attempts[key] = attempt
        bucket = self._byRequest.setdefault((attempt.tenantId, attempt.requestId), [])
        if attempt.id not in bucket:
            bucket.append(attempt.id)
        if attempt.idempotencyKey:
            fingerprint = _attemptFingerprint(
                tenantId=attempt.tenantId,
                requestId=attempt.requestId,
                attemptNumber=attempt.attemptNumber,
                providerId=attempt.providerId,
                modelId=attempt.modelId,
                usage=attempt.usage,
                costAmount=attempt.costAmount,
                costCurrency=attempt.costCurrency,
                outcome=attempt.outcome,
            )
            self._idempotency.setdefault(
                (attempt.tenantId, attempt.idempotencyKey), (fingerprint, attempt.id)
            )
        return attempt

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def getAttempt(self, tenantId: uuid.UUID | str, attemptId: uuid.UUID | str) -> AIUsageAttempt:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(attemptId, "attemptId")
        attempt = self._attempts.get((tenant, identifier))
        if attempt is None:
            raise AIUsageAttemptNotFound(str(identifier))
        return attempt

    def describeAttempt(
        self, tenantId: uuid.UUID | str, attemptId: uuid.UUID | str
    ) -> AttemptDescriptor:
        attempt = self.getAttempt(tenantId, attemptId)
        return AttemptDescriptor(
            tenantId=attempt.tenantId,
            attemptId=attempt.id,
            requestId=attempt.requestId,
            operationId=attempt.operationId,
            attemptNumber=attempt.attemptNumber,
            providerCode=attempt.providerCode,
            modelCode=attempt.modelCode,
            capabilityCode=attempt.capabilityCode,
            inputTokens=attempt.usage.inputTokens,
            outputTokens=attempt.usage.outputTokens,
            totalTokens=attempt.totalTokens,
            costAmount=attempt.costAmount,
            costCurrency=attempt.costCurrency,
            queueTimeMs=attempt.queueTimeMs,
            contextBuildTimeMs=attempt.contextBuildTimeMs,
            providerTimeMs=attempt.providerTimeMs,
            validationTimeMs=attempt.validationTimeMs,
            totalTimeMs=attempt.totalTimeMs,
            outcome=attempt.outcome,
            errorCode=attempt.errorCode,
            correlationId=attempt.correlationId,
            traceId=attempt.traceId,
            createdAt=attempt.createdAt,
        )

    def listAttempts(
        self,
        tenantId: uuid.UUID | str,
        *,
        requestId: uuid.UUID | str | None = None,
        outcome: str | None = None,
    ) -> tuple[AttemptDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedOutcome = ensureAttemptOutcome(outcome) if outcome else None
        requestFilter = requireUuid(requestId, "requestId") if requestId is not None else None
        descriptors = [
            self.describeAttempt(tenant, attempt.id)
            for (attemptTenant, _), attempt in self._attempts.items()
            if attemptTenant == tenant
            and (requestFilter is None or attempt.requestId == requestFilter)
            and (normalizedOutcome is None or attempt.outcome == normalizedOutcome)
        ]
        return tuple(sorted(descriptors, key=lambda item: (item.createdAt, str(item.attemptId))))

    def requestRollup(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
    ) -> RequestUsageRollup:
        tenant = requireUuid(tenantId, "tenantId")
        request = requireUuid(requestId, "requestId")
        attempts = [
            self._attempts[(tenant, identifier)]
            for identifier in self._byRequest.get((tenant, request), [])
        ]
        if not attempts:
            raise AIUsageAttemptNotFound(str(request))
        currencies = {attempt.costCurrency for attempt in attempts}
        if len(currencies) != 1:
            raise AIConfigurationError("Request usage rollups require a single cost currency.")
        return RequestUsageRollup(
            tenantId=tenant,
            requestId=request,
            attempts=len(attempts),
            succeeded=sum(1 for attempt in attempts if attempt.outcome == "SUCCEEDED"),
            failed=sum(1 for attempt in attempts if attempt.outcome == "FAILED"),
            inputTokens=sum(attempt.usage.inputTokens for attempt in attempts),
            outputTokens=sum(attempt.usage.outputTokens for attempt in attempts),
            totalTokens=sum(attempt.totalTokens for attempt in attempts),
            costAmount=sum((attempt.costAmount for attempt in attempts), Decimal("0")),
            costCurrency=attempts[0].costCurrency,
            totalTimeMs=sum(attempt.totalTimeMs for attempt in attempts),
        )

    def summarize(
        self,
        tenantId: uuid.UUID | str,
        *,
        capabilityCode: str = "",
        modelCode: str = "",
        providerCode: str = "",
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> UsageSummary:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedSince = asUtc(since) if since is not None else None
        normalizedUntil = asUtc(until) if until is not None else None
        attempts = [
            attempt
            for (attemptTenant, _), attempt in self._attempts.items()
            if attemptTenant == tenant
            and (not capabilityCode or attempt.capabilityCode == capabilityCode.strip().upper())
            and (not modelCode or attempt.modelCode == modelCode.strip().upper())
            and (not providerCode or attempt.providerCode == providerCode.strip().upper())
            and (normalizedSince is None or attempt.createdAt >= normalizedSince)
            and (normalizedUntil is None or attempt.createdAt < normalizedUntil)
        ]
        currencies = {attempt.costCurrency for attempt in attempts}
        if len(currencies) > 1:
            raise AIConfigurationError("Usage summaries require a single cost currency.")
        currency = next(iter(currencies)) if currencies else "USD"
        return UsageSummary(
            tenantId=tenant,
            attempts=len(attempts),
            succeeded=sum(1 for attempt in attempts if attempt.outcome == "SUCCEEDED"),
            failed=sum(1 for attempt in attempts if attempt.outcome == "FAILED"),
            inputTokens=sum(attempt.usage.inputTokens for attempt in attempts),
            outputTokens=sum(attempt.usage.outputTokens for attempt in attempts),
            totalTokens=sum(attempt.totalTokens for attempt in attempts),
            costAmount=sum((attempt.costAmount for attempt in attempts), Decimal("0")),
            costCurrency=currency,
            latency=latencyStatistics([attempt.totalTimeMs for attempt in attempts]),
            byCapability=self._breakdown(
                attempts, lambda attempt: attempt.capabilityCode or "UNSET"
            ),
            byModel=self._breakdown(attempts, lambda attempt: attempt.modelCode),
            byProvider=self._breakdown(attempts, lambda attempt: attempt.providerCode),
        )

    def buildUsageRecordedEvent(
        self,
        attempt: AIUsageAttempt,
        *,
        now: datetime | None = None,
    ) -> AIUsageRecorded:
        if not isinstance(attempt, AIUsageAttempt):
            raise ValueError("Usage events require an AIUsageAttempt.")
        return AIUsageRecorded(
            tenantId=attempt.tenantId,
            attemptId=attempt.id,
            requestId=attempt.requestId,
            operationId=attempt.operationId,
            providerCode=attempt.providerCode,
            modelCode=attempt.modelCode,
            capabilityCode=attempt.capabilityCode,
            inputTokens=attempt.usage.inputTokens,
            outputTokens=attempt.usage.outputTokens,
            totalTokens=attempt.totalTokens,
            costAmount=attempt.costAmount,
            costCurrency=attempt.costCurrency,
            totalTimeMs=attempt.totalTimeMs,
            outcome=attempt.outcome,
            correlationId=attempt.correlationId,
            traceId=attempt.traceId,
            recordedAt=asUtc(now) if now is not None else self._now(),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _breakdown(attempts: list[AIUsageAttempt], keyOf: Any) -> tuple[UsageBreakdown, ...]:
        buckets: dict[str, dict[str, Any]] = {}
        for attempt in attempts:
            bucketKey = str(keyOf(attempt) or "UNSET")
            bucket = buckets.setdefault(
                bucketKey,
                {
                    "requests": 0,
                    "inputTokens": 0,
                    "outputTokens": 0,
                    "costAmount": Decimal("0"),
                },
            )
            bucket["requests"] += 1
            bucket["inputTokens"] += attempt.usage.inputTokens
            bucket["outputTokens"] += attempt.usage.outputTokens
            bucket["costAmount"] += attempt.costAmount
        return tuple(
            UsageBreakdown(
                key=bucketKey,
                requests=bucket["requests"],
                inputTokens=bucket["inputTokens"],
                outputTokens=bucket["outputTokens"],
                totalTokens=bucket["inputTokens"] + bucket["outputTokens"],
                costAmount=bucket["costAmount"],
            )
            for bucketKey, bucket in sorted(buckets.items())
        )

    def _duplicateAttemptNumber(
        self, tenant: uuid.UUID, request: uuid.UUID, attemptNumber: int
    ) -> bool:
        for attemptId in self._byRequest.get((tenant, request), []):
            if self._attempts[(tenant, attemptId)].attemptNumber == attemptNumber:
                return True
        return False


UsageMeter = UsageMeteringService
InMemoryUsageMetering = UsageMeteringService
AIUsageMeteringService = UsageMeteringService

__all__ = [
    "AIUsageMeteringService",
    "AIUsageRecorded",
    "AttemptDescriptor",
    "CostCalculator",
    "InMemoryUsageMetering",
    "LatencyStats",
    "RequestUsageRollup",
    "UsageBreakdown",
    "UsageMeter",
    "UsageMeteringService",
    "UsageSummary",
    "attemptFingerprint",
    "latencyStatistics",
]
