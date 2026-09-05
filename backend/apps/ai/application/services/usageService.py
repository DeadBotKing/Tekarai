"""Application orchestration for Phase 13-N metering (Django-aware).

``UsageApplicationService`` wires the pure domain coordinators
(``UsageMeteringService``, ``QuotaEnforcementService``) to the persistence
ports, the model rate resolver, the usage event sink, and the
configuration-driven platform defaults (§42). It owns no business rule
itself: every decision (idempotency, exhaustion, cost math, window math)
delegates to the domain layer.

Persistence split (same as Phase 13-G):

- admission (``admitRequest``) is a dry run — it mutates nothing;
- recording (``recordProviderAttempt``) evaluates first, then persists the
  attempt and consumes quota through atomic counter increments;
- reads hydrate transient domain services from the stores on every call,
  so no cross-request in-memory state exists at this layer.

Concurrency note: evaluation and consumption are separate store calls, so
two racing admissions can both pass and then both consume (documented
limitation for the sub-phase P worker serialization; counters themselves
never lose increments because ``addConsumption`` is atomic per row).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.usageRecords import AIQuotaCounter, AIQuotaPolicy, AIUsageAttempt
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIIdempotencyConflict,
    AITokenLimitExceeded,
)
from apps.ai.domain.meteringPorts import (
    CostRateResolver,
    QuotaCounterStore,
    QuotaPolicyStore,
    UsageAttemptStore,
    UsageEventSink,
)
from apps.ai.domain.services.quotaEnforcement import (
    PolicyDescriptor,
    QuotaEnforcementService,
    QuotaRemaining,
    raiseForDenial,
)
from apps.ai.domain.services.usageMetering import (
    AIUsageRecorded,
    AttemptDescriptor,
    CostCalculator,
    RequestUsageRollup,
    UsageMeteringService,
    UsageSummary,
    attemptFingerprint,
)
from apps.ai.domain.valueObjects.aiTypes import CostRate, Money, TokenUsage
from apps.ai.domain.valueObjects.usageTypes import UsageAttribution, asUtc


@dataclass(frozen=True)
class UsageMeteringSettings:
    """Configuration-driven platform defaults (§42 — never hardcoded)."""

    enabled: bool = True
    defaultTokenLimit: int = 0
    defaultCostLimit: Money = Money(Decimal("0"), "USD")
    retentionDays: int = 90

    def __post_init__(self) -> None:
        if not isinstance(self.defaultTokenLimit, int) or isinstance(self.defaultTokenLimit, bool):
            raise ValueError("Default token limit must be an integer.")
        if self.defaultTokenLimit < 0 or self.retentionDays < 1:
            raise ValueError("Metering settings are out of range.")

    @classmethod
    def fromDjangoSettings(cls) -> UsageMeteringSettings:
        currency = str(getattr(djangoSettings, "AI_USAGE_DEFAULT_CURRENCY", "USD") or "USD")
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_USAGE_ENABLED", True)),
            defaultTokenLimit=int(getattr(djangoSettings, "AI_USAGE_DEFAULT_TOKEN_LIMIT", 0) or 0),
            defaultCostLimit=Money(
                Decimal(str(getattr(djangoSettings, "AI_USAGE_DEFAULT_COST_LIMIT", "0") or "0")),
                currency,
            ),
            retentionDays=int(getattr(djangoSettings, "AI_USAGE_RETENTION_DAYS", 90) or 90),
        )


@dataclass(frozen=True)
class RecordUsageAttemptCommand:
    """One metered provider attempt with all §26/§27 measurements."""

    requestId: uuid.UUID
    modelId: uuid.UUID
    providerId: uuid.UUID
    providerCode: str
    modelCode: str
    inputTokens: int
    outputTokens: int
    operationId: uuid.UUID | None = None
    attemptNumber: int = 1
    capabilityCode: str = ""
    requestedBy: uuid.UUID | None = None
    userId: str = ""
    departmentCode: str = ""
    projectId: str = ""
    queueTimeMs: int = 0
    contextBuildTimeMs: int = 0
    providerTimeMs: int = 0
    validationTimeMs: int = 0
    latencyMs: int = 0
    outcome: str = "SUCCEEDED"
    errorCode: str = ""
    idempotencyKey: str = ""
    correlationId: str = ""
    traceId: str = ""
    maxInputTokens: int | None = None

    def attribution(self) -> UsageAttribution:
        return UsageAttribution(
            capabilityCode=self.capabilityCode,
            modelCode=self.modelCode,
            providerCode=self.providerCode,
            userId=self.userId or (str(self.requestedBy) if self.requestedBy else ""),
            departmentCode=self.departmentCode,
            projectId=self.projectId,
        )

    def usage(self) -> TokenUsage:
        return TokenUsage(inputTokens=self.inputTokens, outputTokens=self.outputTokens)


@dataclass(frozen=True)
class AdmissionGrant:
    tenantId: uuid.UUID
    evaluatedAt: datetime
    remaining: tuple[QuotaRemaining, ...] = ()


@dataclass(frozen=True)
class RecordedAttempt:
    attempt: AIUsageAttempt
    counters: tuple[AIQuotaCounter, ...]
    event: AIUsageRecorded


class UsageApplicationService:
    """Tenant-scoped application facade for metering, cost, and quota."""

    def __init__(
        self,
        attemptStore: UsageAttemptStore,
        policyStore: QuotaPolicyStore,
        counterStore: QuotaCounterStore,
        rateResolver: CostRateResolver,
        eventSink: UsageEventSink,
        *,
        meteringSettings: UsageMeteringSettings | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.attemptStore = attemptStore
        self.policyStore = policyStore
        self.counterStore = counterStore
        self.rateResolver = rateResolver
        self.eventSink = eventSink
        self.meteringSettings = meteringSettings or UsageMeteringSettings.fromDjangoSettings()
        self._now = now

    # ------------------------------------------------------------------
    # Quota policy administration (explicit policies; Z exposes them)
    # ------------------------------------------------------------------
    def defineQuotaPolicy(
        self,
        tenantId: uuid.UUID | str,
        scope: str,
        scopeReference: str,
        dimension: str,
        window: str,
        limitValue: Decimal | int | str,
        *,
        currency: str = "USD",
        description: str = "",
    ) -> AIQuotaPolicy:
        tenant = requireUuid(tenantId, "tenantId")
        enforcement = QuotaEnforcementService(now=self._now)
        policy = enforcement.definePolicy(
            tenant,
            scope,
            scopeReference,
            dimension,
            window,
            limitValue,
            currency=currency,
            description=description,
        )
        return self.policyStore.savePolicy(policy)

    def deactivateQuotaPolicy(
        self,
        tenantId: uuid.UUID | str,
        policyId: uuid.UUID | str,
    ) -> AIQuotaPolicy:
        tenant = requireUuid(tenantId, "tenantId")
        return self.policyStore.setPolicyActive(tenant, requireUuid(policyId, "policyId"), False)

    def listQuotaPolicies(self, tenantId: uuid.UUID | str) -> tuple[PolicyDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        enforcement = QuotaEnforcementService(now=self._now)
        for policy in self.policyStore.listActivePolicies(tenant):
            enforcement.importPolicy(policy)
        return enforcement.listPolicies(tenant, activeOnly=True)

    # ------------------------------------------------------------------
    # Admission (dry run — mutates nothing)
    # ------------------------------------------------------------------
    def admitRequest(
        self,
        tenantId: uuid.UUID | str,
        attribution: UsageAttribution,
        *,
        estimatedInputTokens: int = 0,
        estimatedOutputTokens: int = 0,
        estimatedCost: Money | None = None,
        now: datetime | None = None,
    ) -> AdmissionGrant:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        usage = TokenUsage(inputTokens=estimatedInputTokens, outputTokens=estimatedOutputTokens)
        cost = estimatedCost or Money(Decimal("0"), self.meteringSettings.defaultCostLimit.currency)
        self._assertTokenCaps(usage, maxInputTokens=None)
        CostCalculator.assertWithinLimit(cost, self._effectiveCostCap(cost.currency))
        enforcement = self._hydratedEnforcement(tenant, attribution, moment=now)
        evaluation = enforcement.evaluate(tenant, attribution, usage, cost, now=now or self._now())
        if not evaluation.allowed:
            raiseForDenial(evaluation.denials[0])
        return AdmissionGrant(
            tenantId=tenant,
            evaluatedAt=evaluation.evaluatedAt,
            remaining=enforcement.peekRemaining(tenant, attribution, now=now or self._now()),
        )

    # ------------------------------------------------------------------
    # Recording (evaluate → persist attempt → consume → publish)
    # ------------------------------------------------------------------
    def recordProviderAttempt(
        self,
        tenantId: uuid.UUID | str,
        command: RecordUsageAttemptCommand,
        *,
        now: datetime | None = None,
    ) -> RecordedAttempt:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, RecordUsageAttemptCommand):
            raise ValueError("Recording requires a RecordUsageAttemptCommand.")
        usage = command.usage()
        rate = self.rateResolver.rateFor(tenant, command.modelId)
        if not isinstance(rate, CostRate):
            raise AIConfigurationError("Cost rate resolver must return a CostRate.")
        cost = CostCalculator.calculate(usage, rate)
        self._assertTokenCaps(usage, maxInputTokens=command.maxInputTokens)
        CostCalculator.assertWithinLimit(cost, self._effectiveCostCap(cost.currency))
        attribution = command.attribution()
        metering = UsageMeteringService(now=self._now)
        replayed = self._replayIfRecorded(tenant, command, cost, metering)
        if replayed is not None:
            return replayed
        enforcement = self._hydratedEnforcement(tenant, attribution, moment=now)
        evaluation = enforcement.evaluate(tenant, attribution, usage, cost, now=now or self._now())
        if not evaluation.allowed:
            raiseForDenial(evaluation.denials[0])
        attempt = self._buildAttempt(tenant, command, cost, metering)
        stored = self.attemptStore.saveAttempt(attempt)
        counters = self._consumeForPolicies(
            tenant, enforcement, attribution, usage, cost, moment=now
        )
        event = metering.buildUsageRecordedEvent(stored)
        self.eventSink.publish(event)
        return RecordedAttempt(attempt=stored, counters=counters, event=event)

    # ------------------------------------------------------------------
    # Reads (§26 reportable aggregates)
    # ------------------------------------------------------------------
    def describeAttempt(
        self,
        tenantId: uuid.UUID | str,
        attemptId: uuid.UUID | str,
    ) -> AttemptDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        metering = UsageMeteringService(now=self._now)
        metering.importAttempt(
            self.attemptStore.getAttempt(tenant, requireUuid(attemptId, "attemptId"))
        )
        return metering.describeAttempt(tenant, attemptId)

    def listAttempts(
        self,
        tenantId: uuid.UUID | str,
        *,
        requestId: uuid.UUID | str | None = None,
        outcome: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> tuple[AttemptDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        metering = UsageMeteringService(now=self._now)
        for attempt in self.attemptStore.listAttempts(
            tenant,
            requestId=requestId,
            outcome=outcome,
            since=since,
            until=until,
        ):
            metering.importAttempt(attempt)
        return metering.listAttempts(tenant, requestId=requestId, outcome=outcome)

    def requestRollup(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
    ) -> RequestUsageRollup:
        tenant = requireUuid(tenantId, "tenantId")
        metering = UsageMeteringService(now=self._now)
        for attempt in self.attemptStore.listAttempts(tenant, requestId=requestId):
            metering.importAttempt(attempt)
        return metering.requestRollup(tenant, requestId)

    def usageSummary(
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
        metering = UsageMeteringService(now=self._now)
        for attempt in self.attemptStore.listAttempts(tenant, since=since, until=until):
            metering.importAttempt(attempt)
        return metering.summarize(
            tenant,
            capabilityCode=capabilityCode,
            modelCode=modelCode,
            providerCode=providerCode,
            since=since,
            until=until,
        )

    def remainingQuotas(
        self,
        tenantId: uuid.UUID | str,
        attribution: UsageAttribution,
        *,
        now: datetime | None = None,
    ) -> tuple[QuotaRemaining, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        enforcement = self._hydratedEnforcement(tenant, attribution, moment=now)
        return enforcement.peekRemaining(tenant, attribution, now=now or self._now())

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------
    def _buildAttempt(
        self,
        tenant: uuid.UUID,
        command: RecordUsageAttemptCommand,
        cost: Money,
        metering: UsageMeteringService,
    ) -> AIUsageAttempt:
        return metering.recordAttempt(
            tenant,
            command.requestId,
            command.providerId,
            command.modelId,
            providerCode=command.providerCode,
            modelCode=command.modelCode,
            inputTokens=command.inputTokens,
            outputTokens=command.outputTokens,
            costAmount=cost.amount,
            costCurrency=cost.currency,
            queueTimeMs=command.queueTimeMs,
            contextBuildTimeMs=command.contextBuildTimeMs,
            providerTimeMs=command.providerTimeMs,
            validationTimeMs=command.validationTimeMs,
            latencyMs=command.latencyMs,
            attemptNumber=command.attemptNumber,
            operationId=command.operationId,
            capabilityCode=command.capabilityCode,
            requestedBy=command.requestedBy,
            outcome=command.outcome,
            errorCode=command.errorCode,
            idempotencyKey=command.idempotencyKey,
            correlationId=command.correlationId,
            traceId=command.traceId,
        )

    def _replayIfRecorded(
        self,
        tenant: uuid.UUID,
        command: RecordUsageAttemptCommand,
        cost: Money,
        metering: UsageMeteringService,
    ) -> RecordedAttempt | None:
        """Return stored state for a repeated idempotency key (no side effects).

        A replay performs no consumption and no publication: side effects
        happen exactly once per key. A reused key with different content
        raises ``AIIdempotencyConflict`` instead.
        """

        key = str(command.idempotencyKey or "").strip()
        if not key:
            return None
        existing = self.attemptStore.findByIdempotencyKey(tenant, key)
        if existing is None:
            return None
        candidate = self._buildAttempt(tenant, command, cost, UsageMeteringService(now=self._now))
        if attemptFingerprint(candidate) != attemptFingerprint(existing):
            raise AIIdempotencyConflict(
                "The tenant-scoped usage idempotency key is already bound to another attempt."
            )
        enforcement = self._hydratedEnforcement(tenant, command.attribution())
        current = self._now()
        counters = tuple(
            counter
            for policy in enforcement.matchingPolicies(tenant, command.attribution())
            for counter in [
                enforcement.counterForWindow(tenant, policy.id, policy.windowStartFor(current))
            ]
            if counter is not None
        )
        event = metering.buildUsageRecordedEvent(existing)
        return RecordedAttempt(attempt=existing, counters=counters, event=event)

    def _requireEnabled(self) -> None:
        if not self.meteringSettings.enabled:
            raise AIConfigurationError("AI usage metering is disabled by configuration.")

    def _effectiveCostCap(self, currency: str) -> Money:
        configured = self.meteringSettings.defaultCostLimit
        if configured.currency != currency:
            # Unlimited in a foreign currency would silently bypass the cap;
            # fail closed instead (contract §N.6).
            return Money(Decimal("0"), currency)
        if configured.amount <= 0:
            return Money(Decimal("10") ** 18, currency)
        return configured

    def _assertTokenCaps(self, usage: TokenUsage, *, maxInputTokens: int | None) -> None:
        if maxInputTokens is not None and usage.inputTokens > maxInputTokens:
            raise AITokenLimitExceeded(
                f"AI input tokens {usage.inputTokens} exceed the {maxInputTokens} limit."
            )
        defaultLimit = self.meteringSettings.defaultTokenLimit
        if defaultLimit > 0 and usage.totalTokens > defaultLimit:
            raise AITokenLimitExceeded(
                f"AI total tokens {usage.totalTokens} exceed the {defaultLimit} limit."
            )

    def _hydratedEnforcement(
        self,
        tenant: uuid.UUID,
        attribution: UsageAttribution,
        *,
        moment: datetime | None = None,
    ) -> QuotaEnforcementService:
        enforcement = QuotaEnforcementService(now=self._now)
        policies = [policy for policy in self.policyStore.listActivePolicies(tenant)]
        for policy in policies:
            enforcement.importPolicy(policy)
        current = asUtc(moment) if moment is not None else self._now()
        for policy in policies:
            if not policy.matches(attribution):
                continue
            start = policy.windowStartFor(current)
            counter = self.counterStore.loadCounter(tenant, policy.id, start)
            if counter is not None:
                enforcement.importCounter(counter)
        return enforcement

    def _consumeForPolicies(
        self,
        tenant: uuid.UUID,
        enforcement: QuotaEnforcementService,
        attribution: UsageAttribution,
        usage: TokenUsage,
        cost: Money,
        *,
        moment: datetime | None = None,
    ) -> tuple[AIQuotaCounter, ...]:
        current = asUtc(moment) if moment is not None else self._now()
        consumed: list[AIQuotaCounter] = []
        for policy in enforcement.matchingPolicies(tenant, attribution):
            start = policy.windowStartFor(current)
            counterCurrency = policy.currency
            amount = cost.amount if policy.dimension == "COST" else Decimal("0")
            consumed.append(
                self.counterStore.addConsumption(
                    tenant,
                    policy.id,
                    start,
                    requests=1,
                    inputTokens=usage.inputTokens,
                    outputTokens=usage.outputTokens,
                    costAmount=amount,
                    currency=counterCurrency,
                )
            )
        return tuple(consumed)


UsageMeteringApplicationService = UsageApplicationService
AIUsageService = UsageApplicationService

__all__ = [
    "AIUsageService",
    "AdmissionGrant",
    "RecordUsageAttemptCommand",
    "RecordedAttempt",
    "UsageApplicationService",
    "UsageMeteringApplicationService",
    "UsageMeteringSettings",
]
