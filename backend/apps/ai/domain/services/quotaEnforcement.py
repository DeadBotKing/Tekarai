"""Pure quota policy registry and enforcement for Phase 13-N.

``QuotaEnforcementService`` is a tenant-scoped in-memory coordinator that
owns quota policies and their per-window counters. Enforcement is
fail-closed and atomic at the domain level: every matching active policy
is evaluated before any counter is mutated, so a denied attempt never
leaves partial consumption behind.

Matching semantics (§N.4):

- every active policy whose scope matches the attempt attribution applies —
  a tenant cap and a user cap can deny independently;
- denial messages list the most specific policy first (``SCOPE_PRECEDENCE``);
- consumption is outcome-agnostic: failed attempts consume quota because
  providers bill failed calls;
- a new window starts a fresh counter; old windows stay readable.

The service is provider-agnostic and persistence-free; an application
adapter hydrates policies/counters from its stores and persists the
resulting consumption (the same split as Phase 13-G).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.usageRecords import AIQuotaCounter, AIQuotaPolicy
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AICostLimitExceeded,
    AIError,
    AIQuotaExceeded,
    AIQuotaPolicyAlreadyRegistered,
    AIQuotaPolicyInvalid,
    AIQuotaPolicyNotFound,
)
from apps.ai.domain.valueObjects.aiTypes import Money, TokenUsage
from apps.ai.domain.valueObjects.usageTypes import (
    SCOPE_PRECEDENCE,
    UsageAttribution,
    asUtc,
    windowEnd,
)


@dataclass(frozen=True)
class PolicyDescriptor:
    """Safe quota policy read model."""

    tenantId: uuid.UUID
    policyId: uuid.UUID
    scope: str
    scopeReference: str
    dimension: str
    window: str
    limitValue: Decimal
    currency: str
    description: str
    isActive: bool
    createdAt: datetime
    updatedAt: datetime


@dataclass(frozen=True)
class ConsumedQuota:
    policyId: uuid.UUID
    scope: str
    dimension: str
    window: str
    windowStart: datetime
    consumed: Decimal | int
    limitValue: Decimal


@dataclass(frozen=True)
class QuotaConsumption:
    tenantId: uuid.UUID
    evaluatedAt: datetime
    consumed: tuple[ConsumedQuota, ...] = ()


@dataclass(frozen=True)
class QuotaRemaining:
    policyId: uuid.UUID
    scope: str
    dimension: str
    window: str
    windowStart: datetime
    windowEnd: datetime
    remaining: Decimal | int
    limitValue: Decimal


@dataclass(frozen=True)
class PolicyDenial:
    """One policy that denied an attempt (most specific first)."""

    policyId: uuid.UUID
    scope: str
    dimension: str
    window: str
    windowStart: datetime
    limitValue: Decimal
    consumed: Decimal | int


@dataclass(frozen=True)
class QuotaEvaluation:
    """Dry-run enforcement verdict; mutates nothing."""

    tenantId: uuid.UUID
    evaluatedAt: datetime
    allowed: bool
    denials: tuple[PolicyDenial, ...] = ()


def raiseForDenial(denial: PolicyDenial) -> None:
    """Raise the stable domain error for a denial (single message source)."""

    if denial.dimension == "COST":
        raise AICostLimitExceeded(
            f"AI cost quota exhausted for {denial.scope} {denial.window} "
            f"(limit {denial.limitValue})."
        )
    raise AIQuotaExceeded(
        f"AI {denial.dimension} quota exhausted for {denial.scope} "
        f"{denial.window} (limit {denial.limitValue}, consumed {denial.consumed})."
    )


@dataclass
class PolicyRegistration:
    policy: AIQuotaPolicy
    counters: dict[datetime, AIQuotaCounter] = field(default_factory=dict)


def _policyKey(
    tenantId: uuid.UUID,
    scope: str,
    scopeReference: str,
    dimension: str,
    window: str,
) -> tuple[uuid.UUID, str, str, str, str]:
    return (tenantId, scope, scopeReference, dimension, window)


def _precedenceIndex(scope: str) -> int:
    try:
        return SCOPE_PRECEDENCE.index(scope)
    except ValueError:
        return len(SCOPE_PRECEDENCE)


def _coerceLimit(limitValue: Decimal | int | str) -> Decimal:
    """Coerce caller-supplied limits; business invariants stay in the entity."""

    if isinstance(limitValue, Decimal):
        return limitValue
    try:
        return Decimal(str(limitValue))
    except Exception as exc:
        raise AIQuotaPolicyInvalid(f"Quota limit {limitValue!r} is invalid.") from exc


class QuotaEnforcementService:
    """Tenant-scoped in-memory registry and enforcer for quota policies."""

    def __init__(self, *, now: Any = utcNow) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._now = now
        self._policies: dict[tuple[uuid.UUID, str, str, str, str], PolicyRegistration] = {}
        self._byId: dict[tuple[uuid.UUID, uuid.UUID], tuple[uuid.UUID, str, str, str, str]] = {}

    # ------------------------------------------------------------------
    # Policy registry
    # ------------------------------------------------------------------
    def definePolicy(
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
        policyId: uuid.UUID | str | None = None,
    ) -> AIQuotaPolicy:
        tenant = requireUuid(tenantId, "tenantId")
        try:
            policy = AIQuotaPolicy(
                tenantId=tenant,
                scope=scope,
                scopeReference=scopeReference,
                dimension=dimension,
                window=window,
                limitValue=_coerceLimit(limitValue),
                id=requireUuid(policyId, "policyId") if policyId is not None else uuid.uuid4(),
                currency=currency,
                description=description,
                isActive=True,
                createdAt=self._now(),
                updatedAt=self._now(),
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIQuotaPolicyInvalid(str(exc)) from exc
        key = _policyKey(
            tenant, policy.scope, policy.scopeReference, policy.dimension, policy.window
        )
        if key in self._policies:
            raise AIQuotaPolicyAlreadyRegistered(
                f"Quota policy {policy.scope}/{policy.dimension}/{policy.window} is already defined."
            )
        identifier = (tenant, policy.id)
        if identifier in self._byId:
            raise AIQuotaPolicyAlreadyRegistered("Quota policy id is already registered.")
        self._policies[key] = PolicyRegistration(policy=policy)
        self._byId[identifier] = key
        return policy

    def importPolicy(self, policy: AIQuotaPolicy) -> AIQuotaPolicy:
        """Load a persisted policy (application hydration)."""

        if not isinstance(policy, AIQuotaPolicy):
            raise ValueError("Only AIQuotaPolicy records can be imported.")
        key = _policyKey(
            policy.tenantId, policy.scope, policy.scopeReference, policy.dimension, policy.window
        )
        existing = self._policies.get(key)
        if existing is not None and existing.policy.id != policy.id:
            raise AIQuotaPolicyAlreadyRegistered("A different policy owns this quota axis.")
        self._policies[key] = PolicyRegistration(policy=policy)
        self._byId[(policy.tenantId, policy.id)] = key
        return policy

    def importCounter(self, counter: AIQuotaCounter) -> AIQuotaCounter:
        """Load a persisted window counter (application hydration)."""

        if not isinstance(counter, AIQuotaCounter):
            raise ValueError("Only AIQuotaCounter records can be imported.")
        registration = self._registrationForPolicy(counter.tenantId, counter.policyId)
        registration.counters[counter.windowStart] = counter
        return counter

    def getPolicy(self, tenantId: uuid.UUID | str, policyId: uuid.UUID | str) -> AIQuotaPolicy:
        return self._registrationForPolicy(tenantId, policyId).policy

    def describePolicy(
        self, tenantId: uuid.UUID | str, policyId: uuid.UUID | str
    ) -> PolicyDescriptor:
        policy = self.getPolicy(tenantId, policyId)
        return PolicyDescriptor(
            tenantId=policy.tenantId,
            policyId=policy.id,
            scope=policy.scope,
            scopeReference=policy.scopeReference,
            dimension=policy.dimension,
            window=policy.window,
            limitValue=policy.limitValue,
            currency=policy.currency,
            description=policy.description,
            isActive=policy.isActive,
            createdAt=policy.createdAt,
            updatedAt=policy.updatedAt,
        )

    def listPolicies(
        self,
        tenantId: uuid.UUID | str,
        *,
        activeOnly: bool = False,
    ) -> tuple[PolicyDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        descriptors = [
            self.describePolicy(tenant, registration.policy.id)
            for (policyTenant, _), key in self._byId.items()
            if policyTenant == tenant
            for registration in [self._policies[key]]
            if not activeOnly or registration.policy.isActive
        ]
        return tuple(
            sorted(
                descriptors,
                key=lambda item: (
                    _precedenceIndex(item.scope),
                    item.dimension,
                    item.window,
                    item.scopeReference,
                ),
            )
        )

    def updatePolicyLimit(
        self,
        tenantId: uuid.UUID | str,
        policyId: uuid.UUID | str,
        limitValue: Decimal | int | str,
        *,
        now: datetime | None = None,
    ) -> AIQuotaPolicy:
        registration = self._registrationForPolicy(tenantId, policyId)
        policy = registration.policy
        try:
            candidate = AIQuotaPolicy(
                tenantId=policy.tenantId,
                scope=policy.scope,
                scopeReference=policy.scopeReference,
                dimension=policy.dimension,
                window=policy.window,
                limitValue=_coerceLimit(limitValue),
                id=policy.id,
                currency=policy.currency,
                description=policy.description,
                isActive=policy.isActive,
                createdAt=policy.createdAt,
                updatedAt=asUtc(now) if now is not None else self._now(),
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIQuotaPolicyInvalid(str(exc)) from exc
        registration.policy = candidate
        return candidate

    def deactivatePolicy(
        self,
        tenantId: uuid.UUID | str,
        policyId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIQuotaPolicy:
        registration = self._registrationForPolicy(tenantId, policyId)
        registration.policy.deactivate(now=now or self._now())
        return registration.policy

    def activatePolicy(
        self,
        tenantId: uuid.UUID | str,
        policyId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIQuotaPolicy:
        registration = self._registrationForPolicy(tenantId, policyId)
        registration.policy.activate(now=now or self._now())
        return registration.policy

    # ------------------------------------------------------------------
    # Enforcement
    # ------------------------------------------------------------------
    def matchingPolicies(
        self,
        tenantId: uuid.UUID | str,
        attribution: UsageAttribution,
    ) -> tuple[AIQuotaPolicy, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        if not isinstance(attribution, UsageAttribution):
            raise ValueError("Quota matching requires a UsageAttribution.")
        matched = [
            registration.policy
            for (policyTenant, _), key in self._byId.items()
            if policyTenant == tenant
            for registration in [self._policies[key]]
            if registration.policy.isActive and registration.policy.matches(attribution)
        ]
        return tuple(sorted(matched, key=lambda policy: _precedenceIndex(policy.scope)))

    def peekRemaining(
        self,
        tenantId: uuid.UUID | str,
        attribution: UsageAttribution,
        *,
        now: datetime | None = None,
    ) -> tuple[QuotaRemaining, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        moment = asUtc(now) if now is not None else self._now()
        remaining: list[QuotaRemaining] = []
        for policy in self.matchingPolicies(tenant, attribution):
            start = policy.windowStartFor(moment)
            counter = self._counterFor(policy, start, create=False)
            available: Decimal | int = (
                counter.remainingFor(policy) if counter is not None else policy.limit()
            )
            remaining.append(
                QuotaRemaining(
                    policyId=policy.id,
                    scope=policy.scope,
                    dimension=policy.dimension,
                    window=policy.window,
                    windowStart=start,
                    windowEnd=windowEnd(start, policy.window),
                    remaining=available,
                    limitValue=policy.limitValue,
                )
            )
        return tuple(remaining)

    def evaluate(
        self,
        tenantId: uuid.UUID | str,
        attribution: UsageAttribution,
        usage: TokenUsage,
        cost: Money,
        *,
        now: datetime | None = None,
    ) -> QuotaEvaluation:
        """Dry-run enforcement verdict over the current counters.

        Nothing is mutated, so application adapters can admit work before
        persisting it, then consume atomically through their counter store.
        """

        tenant, moment, policies = self._validatedInputs(tenantId, attribution, usage, cost, now)
        denials: list[PolicyDenial] = []
        for policy in policies:
            start = policy.windowStartFor(moment)
            counter = self._counterFor(policy, start, create=False)
            probe = counter or self._emptyCounter(tenant, policy, start)
            if probe.isExhaustedBy(policy, usage, cost):
                consumed = counter.consumedFor(policy.dimension) if counter is not None else 0
                denials.append(
                    PolicyDenial(
                        policyId=policy.id,
                        scope=policy.scope,
                        dimension=policy.dimension,
                        window=policy.window,
                        windowStart=start,
                        limitValue=policy.limitValue,
                        consumed=consumed,
                    )
                )
        return QuotaEvaluation(
            tenantId=tenant,
            evaluatedAt=moment,
            allowed=not denials,
            denials=tuple(denials),
        )

    def checkAndConsume(
        self,
        tenantId: uuid.UUID | str,
        attribution: UsageAttribution,
        usage: TokenUsage,
        cost: Money,
        *,
        now: datetime | None = None,
    ) -> QuotaConsumption:
        """Evaluate every matching policy, then consume exactly once.

        Raises ``AIQuotaExceeded`` (or ``AICostLimitExceeded`` for COST
        dimensions) without mutating any counter when a single policy
        denies the attempt.
        """

        tenant, moment, policies = self._validatedInputs(tenantId, attribution, usage, cost, now)
        evaluation = self.evaluate(tenant, attribution, usage, cost, now=moment)
        if not evaluation.allowed:
            raiseForDenial(evaluation.denials[0])
        consumedQuotas: list[ConsumedQuota] = []
        for policy in policies:
            start = policy.windowStartFor(moment)
            counter = self._counterFor(policy, start, create=True)
            assert counter is not None
            counter.addConsumption(usage, self._scopedCost(policy, cost), now=moment)
            consumedQuotas.append(
                ConsumedQuota(
                    policyId=policy.id,
                    scope=policy.scope,
                    dimension=policy.dimension,
                    window=policy.window,
                    windowStart=start,
                    consumed=counter.consumedFor(policy.dimension),
                    limitValue=policy.limitValue,
                )
            )
        return QuotaConsumption(tenantId=tenant, evaluatedAt=moment, consumed=tuple(consumedQuotas))

    def counterForWindow(
        self,
        tenantId: uuid.UUID | str,
        policyId: uuid.UUID | str,
        windowStartValue: datetime,
    ) -> AIQuotaCounter | None:
        registration = self._registrationForPolicy(tenantId, policyId)
        return registration.counters.get(asUtc(windowStartValue))

    # ------------------------------------------------------------------
    # Internal invariants
    # ------------------------------------------------------------------
    def _validatedInputs(
        self,
        tenantId: uuid.UUID | str,
        attribution: UsageAttribution,
        usage: TokenUsage,
        cost: Money,
        now: datetime | None,
    ) -> tuple[uuid.UUID, datetime, tuple[AIQuotaPolicy, ...]]:
        tenant = requireUuid(tenantId, "tenantId")
        if not isinstance(attribution, UsageAttribution):
            raise ValueError("Quota enforcement requires a UsageAttribution.")
        if not isinstance(usage, TokenUsage) or not isinstance(cost, Money):
            raise ValueError("Quota enforcement requires TokenUsage and Money values.")
        moment = asUtc(now) if now is not None else self._now()
        policies = self.matchingPolicies(tenant, attribution)
        self._assertCurrencyCompatibility(policies, cost)
        return tenant, moment, policies

    def _registrationForPolicy(
        self,
        tenantId: uuid.UUID | str,
        policyId: uuid.UUID | str,
    ) -> PolicyRegistration:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(policyId, "policyId")
        key = self._byId.get((tenant, identifier))
        if key is None:
            raise AIQuotaPolicyNotFound(str(identifier))
        return self._policies[key]

    def _counterFor(
        self,
        policy: AIQuotaPolicy,
        start: datetime,
        *,
        create: bool,
    ) -> AIQuotaCounter | None:
        registration = self._registrationForPolicy(policy.tenantId, policy.id)
        counter = registration.counters.get(start)
        if counter is None and create:
            counter = self._emptyCounter(policy.tenantId, policy, start)
            registration.counters[start] = counter
        return counter

    @staticmethod
    def _emptyCounter(
        tenantId: uuid.UUID,
        policy: AIQuotaPolicy,
        start: datetime,
    ) -> AIQuotaCounter:
        return AIQuotaCounter(
            tenantId=tenantId,
            policyId=policy.id,
            windowStart=start,
            currency=policy.currency,
        )

    @staticmethod
    def _assertCurrencyCompatibility(policies: tuple[AIQuotaPolicy, ...], cost: Money) -> None:
        for policy in policies:
            if policy.dimension == "COST" and policy.currency != cost.currency:
                raise AIConfigurationError(
                    "Cost quota currency must match the attempt cost currency."
                )

    @staticmethod
    def _scopedCost(policy: AIQuotaPolicy, cost: Money) -> Money:
        if policy.dimension == "COST":
            return cost
        # Non-cost counters track a zero amount in the policy currency so the
        # counter currency invariant always holds, whatever the attempt bills.
        return Money(Decimal("0"), policy.currency)


QuotaPolicyService = QuotaEnforcementService
InMemoryQuotaEnforcement = QuotaEnforcementService
AIQuotaService = QuotaEnforcementService

__all__ = [
    "AIQuotaService",
    "ConsumedQuota",
    "InMemoryQuotaEnforcement",
    "PolicyDenial",
    "PolicyDescriptor",
    "PolicyRegistration",
    "QuotaConsumption",
    "QuotaEnforcementService",
    "QuotaEvaluation",
    "QuotaPolicyService",
    "QuotaRemaining",
    "raiseForDenial",
]
