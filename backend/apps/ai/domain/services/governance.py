"""Pure AI governance policy registry and evaluation (Phase 13-O).

``GovernanceService`` is a tenant-scoped in-memory coordinator that owns
at most one enforceable governance policy per tenant (§48) and evaluates
governance requests against it. Evaluation is fail-closed with a fixed
rule order (§O.7.2):

1. disabled capability → DENY;
2. provider outside a non-empty allowlist → DENY;
3. model outside a non-empty allowlist → DENY;
4. RESTRICTED data to an external provider without an explicit
   tenant opt-in → DENY;
5. daily cost budget: currency mismatch → ``AIConfigurationError``;
   projected (day spend + estimate) above a positive budget → DENY;
   unknown day spend skips the rule (documented), never guesses;
6. otherwise ALLOW.

Every evaluation yields one reason per assessed rule, so both ALLOW and
DENY verdicts stay explainable after later policy edits — the application
layer persists each decision with its rule snapshot into the audit trail.

The service is provider-agnostic and persistence-free; an application
adapter hydrates the tenant policy from its store (the same split as the
Phase 13-G/N coordinators).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.auditRecords import (
    AIGovernancePolicy,
    DecisionReason,
    GovernanceDecision,
    GovernanceRequest,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIError,
    AIGovernanceDenied,
    AIGovernancePolicyAlreadyRegistered,
    AIGovernancePolicyInvalid,
    AIGovernancePolicyNotFound,
)
from apps.ai.domain.valueObjects.usageTypes import asUtc


@dataclass(frozen=True)
class GovernancePolicyDescriptor:
    """Safe governance policy read model."""

    tenantId: uuid.UUID
    policyId: uuid.UUID
    name: str
    allowedProviders: tuple[str, ...]
    allowedModels: tuple[str, ...]
    disabledCapabilities: tuple[str, ...]
    allowRestrictedToExternal: bool
    maxCostPerDay: Decimal
    currency: str
    description: str
    isActive: bool
    createdAt: datetime
    updatedAt: datetime


@dataclass(frozen=True)
class GovernanceEvaluation:
    """Dry-run governance verdict; mutates nothing."""

    tenantId: uuid.UUID
    evaluatedAt: datetime
    allowed: bool
    reasons: tuple[DecisionReason, ...]


def _coerceCodes(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """Coerce caller-supplied code lists; business invariants stay in the entity."""

    if values is None:
        return ()
    return tuple(values)


def _coerceBudget(value: Decimal | int | str) -> Decimal:
    """Coerce caller-supplied budgets; business invariants stay in the entity."""

    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception as exc:
        raise AIGovernancePolicyInvalid(f"Governance budget {value!r} is invalid.") from exc


def raiseForDecision(decision: GovernanceDecision) -> None:
    """Raise the stable domain error for a DENY verdict (single source)."""

    if decision.allowed:
        return None
    firstDenial = next((reason for reason in decision.reasons if not reason.allowed), None)
    detail = firstDenial.message if firstDenial is not None else "AI governance denied the request."
    raise AIGovernanceDenied(detail)


class GovernanceService:
    """Tenant-scoped in-memory registry and evaluator for governance."""

    def __init__(self, *, now: Any = utcNow) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._now = now
        self._policies: dict[uuid.UUID, AIGovernancePolicy] = {}
        self._byId: dict[tuple[uuid.UUID, uuid.UUID], uuid.UUID] = {}

    # ------------------------------------------------------------------
    # Policy registry (one policy per tenant)
    # ------------------------------------------------------------------
    def definePolicy(
        self,
        tenantId: uuid.UUID | str,
        *,
        name: str = "default",
        allowedProviders: tuple[str, ...] | list[str] | None = None,
        allowedModels: tuple[str, ...] | list[str] | None = None,
        disabledCapabilities: tuple[str, ...] | list[str] | None = None,
        allowRestrictedToExternal: bool = False,
        maxCostPerDay: Decimal | int | str = Decimal("0"),
        currency: str = "USD",
        description: str = "",
        policyId: uuid.UUID | str | None = None,
    ) -> AIGovernancePolicy:
        tenant = requireUuid(tenantId, "tenantId")
        if tenant in self._policies:
            raise AIGovernancePolicyAlreadyRegistered(
                "A governance policy is already defined for this tenant."
            )
        try:
            policy = AIGovernancePolicy(
                tenantId=tenant,
                id=requireUuid(policyId, "policyId") if policyId is not None else uuid.uuid4(),
                name=name,
                allowedProviders=_coerceCodes(allowedProviders),
                allowedModels=_coerceCodes(allowedModels),
                disabledCapabilities=_coerceCodes(disabledCapabilities),
                allowRestrictedToExternal=allowRestrictedToExternal,
                maxCostPerDay=_coerceBudget(maxCostPerDay),
                currency=currency,
                description=description,
                isActive=True,
                createdAt=self._now(),
                updatedAt=self._now(),
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIGovernancePolicyInvalid(str(exc)) from exc
        identifier = (tenant, policy.id)
        if identifier in self._byId:
            raise AIGovernancePolicyAlreadyRegistered("Governance policy id is already used.")
        self._policies[tenant] = policy
        self._byId[identifier] = tenant
        return policy

    def importPolicy(self, policy: AIGovernancePolicy) -> AIGovernancePolicy:
        """Load a persisted policy (application hydration)."""

        if not isinstance(policy, AIGovernancePolicy):
            raise ValueError("Only AIGovernancePolicy records can be imported.")
        existing = self._policies.get(policy.tenantId)
        if existing is not None and existing.id != policy.id:
            raise AIGovernancePolicyAlreadyRegistered(
                "A different governance policy owns this tenant."
            )
        self._policies[policy.tenantId] = policy
        self._byId[(policy.tenantId, policy.id)] = policy.tenantId
        return policy

    def getPolicy(self, tenantId: uuid.UUID | str) -> AIGovernancePolicy:
        tenant = requireUuid(tenantId, "tenantId")
        policy = self._policies.get(tenant)
        if policy is None:
            raise AIGovernancePolicyNotFound("No governance policy is defined for this tenant.")
        return policy

    def describePolicy(self, tenantId: uuid.UUID | str) -> GovernancePolicyDescriptor:
        policy = self.getPolicy(tenantId)
        return GovernancePolicyDescriptor(
            tenantId=policy.tenantId,
            policyId=policy.id,
            name=policy.name,
            allowedProviders=policy.allowedProviders,
            allowedModels=policy.allowedModels,
            disabledCapabilities=policy.disabledCapabilities,
            allowRestrictedToExternal=policy.allowRestrictedToExternal,
            maxCostPerDay=policy.maxCostPerDay,
            currency=policy.currency,
            description=policy.description,
            isActive=policy.isActive,
            createdAt=policy.createdAt,
            updatedAt=policy.updatedAt,
        )

    def updatePolicy(
        self,
        tenantId: uuid.UUID | str,
        *,
        name: str | None = None,
        allowedProviders: tuple[str, ...] | list[str] | None = None,
        allowedModels: tuple[str, ...] | list[str] | None = None,
        disabledCapabilities: tuple[str, ...] | list[str] | None = None,
        allowRestrictedToExternal: bool | None = None,
        maxCostPerDay: Decimal | int | str | None = None,
        currency: str | None = None,
        description: str | None = None,
        now: datetime | None = None,
    ) -> AIGovernancePolicy:
        current = self.getPolicy(tenantId)
        try:
            candidate = AIGovernancePolicy(
                tenantId=current.tenantId,
                id=current.id,
                name=current.name if name is None else name,
                allowedProviders=current.allowedProviders
                if allowedProviders is None
                else _coerceCodes(allowedProviders),
                allowedModels=current.allowedModels
                if allowedModels is None
                else _coerceCodes(allowedModels),
                disabledCapabilities=current.disabledCapabilities
                if disabledCapabilities is None
                else _coerceCodes(disabledCapabilities),
                allowRestrictedToExternal=current.allowRestrictedToExternal
                if allowRestrictedToExternal is None
                else allowRestrictedToExternal,
                maxCostPerDay=current.maxCostPerDay
                if maxCostPerDay is None
                else _coerceBudget(maxCostPerDay),
                currency=current.currency if currency is None else currency,
                description=current.description if description is None else description,
                isActive=current.isActive,
                createdAt=current.createdAt,
                updatedAt=asUtc(now) if now is not None else self._now(),
            )
        except AIError:
            raise
        except Exception as exc:
            raise AIGovernancePolicyInvalid(str(exc)) from exc
        self._policies[current.tenantId] = candidate
        return candidate

    def deactivatePolicy(
        self, tenantId: uuid.UUID | str, *, now: datetime | None = None
    ) -> AIGovernancePolicy:
        policy = self.getPolicy(tenantId)
        policy.deactivate(now=now or self._now())
        return policy

    def activatePolicy(
        self, tenantId: uuid.UUID | str, *, now: datetime | None = None
    ) -> AIGovernancePolicy:
        policy = self.getPolicy(tenantId)
        policy.activate(now=now or self._now())
        return policy

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate(
        self,
        request: GovernanceRequest,
        policy: AIGovernancePolicy | None = None,
        *,
        now: datetime | None = None,
    ) -> GovernanceEvaluation:
        """Dry-run governance verdict over one request and one policy."""

        if not isinstance(request, GovernanceRequest):
            raise ValueError("Governance evaluation requires a GovernanceRequest.")
        active = policy if policy is not None else self.getPolicy(request.tenantId)
        if not isinstance(active, AIGovernancePolicy):
            raise ValueError("Governance evaluation requires an AIGovernancePolicy.")
        if active.tenantId != request.tenantId:
            raise AIGovernancePolicyNotFound("Governance policy belongs to another tenant.")
        moment = asUtc(now) if now is not None else self._now()
        reasons = self._assessRules(request, active)
        allowed = all(reason.allowed for reason in reasons)
        return GovernanceEvaluation(
            tenantId=request.tenantId,
            evaluatedAt=moment,
            allowed=allowed,
            reasons=tuple(reasons),
        )

    def decide(
        self,
        request: GovernanceRequest,
        policy: AIGovernancePolicy | None = None,
        *,
        now: datetime | None = None,
    ) -> GovernanceDecision:
        evaluation = self.evaluate(request, policy, now=now)
        return GovernanceDecision(
            tenantId=evaluation.tenantId,
            allowed=evaluation.allowed,
            reasons=evaluation.reasons,
            evaluatedAt=evaluation.evaluatedAt,
        )

    # ------------------------------------------------------------------
    # Internal invariants
    # ------------------------------------------------------------------
    @staticmethod
    def _assessRules(
        request: GovernanceRequest, policy: AIGovernancePolicy
    ) -> list[DecisionReason]:
        reasons: list[DecisionReason] = []
        if request.capabilityCode and request.capabilityCode in policy.disabledCapabilities:
            reasons.append(
                DecisionReason(
                    rule="CAPABILITY",
                    allowed=False,
                    message=f"AI capability {request.capabilityCode} is disabled by governance.",
                )
            )
        else:
            reasons.append(
                DecisionReason(rule="CAPABILITY", allowed=True, message="AI capability is enabled.")
            )
        if policy.allowedProviders and request.providerCode not in policy.allowedProviders:
            reasons.append(
                DecisionReason(
                    rule="PROVIDER",
                    allowed=False,
                    message=f"AI provider {request.providerCode or 'UNSET'} is not allowlisted.",
                )
            )
        else:
            reasons.append(
                DecisionReason(rule="PROVIDER", allowed=True, message="AI provider is allowlisted.")
            )
        if policy.allowedModels and request.modelCode not in policy.allowedModels:
            reasons.append(
                DecisionReason(
                    rule="MODEL",
                    allowed=False,
                    message=f"AI model {request.modelCode or 'UNSET'} is not allowlisted.",
                )
            )
        else:
            reasons.append(
                DecisionReason(rule="MODEL", allowed=True, message="AI model is allowlisted.")
            )
        if (
            request.classification == "RESTRICTED"
            and request.providerIsExternal
            and not policy.allowRestrictedToExternal
        ):
            reasons.append(
                DecisionReason(
                    rule="DATA_BOUNDARY",
                    allowed=False,
                    message="RESTRICTED data cannot leave the platform under this policy.",
                )
            )
        else:
            reasons.append(
                DecisionReason(
                    rule="DATA_BOUNDARY", allowed=True, message="Data boundary is satisfied."
                )
            )
        reasons.append(GovernanceService._assessBudget(request, policy))
        return reasons

    @staticmethod
    def _assessBudget(request: GovernanceRequest, policy: AIGovernancePolicy) -> DecisionReason:
        if policy.maxCostPerDay <= 0:
            return DecisionReason(
                rule="COST_BUDGET", allowed=True, message="No daily cost budget is configured."
            )
        if request.daySpend is None:
            return DecisionReason(
                rule="COST_BUDGET",
                allowed=True,
                message="Daily spend is unknown; the budget rule is skipped.",
            )
        if request.daySpend.currency != policy.currency or (
            request.estimatedCost is not None and request.estimatedCost.currency != policy.currency
        ):
            raise AIConfigurationError("Governance budget evaluation requires matching currencies.")
        estimate = (
            request.estimatedCost.amount if request.estimatedCost is not None else Decimal("0")
        )
        projected = request.daySpend.amount + estimate
        if projected > policy.maxCostPerDay:
            return DecisionReason(
                rule="COST_BUDGET",
                allowed=False,
                message=(
                    f"Forecast daily cost {projected} exceeds the "
                    f"{policy.maxCostPerDay} {policy.currency} budget."
                ),
            )
        return DecisionReason(
            rule="COST_BUDGET",
            allowed=True,
            message=f"Forecast daily cost {projected} is within budget.",
        )


GovernancePolicyService = GovernanceService
InMemoryGovernance = GovernanceService
AIGovernanceService = GovernanceService

__all__ = [
    "AIGovernanceService",
    "GovernanceEvaluation",
    "GovernancePolicyDescriptor",
    "GovernancePolicyService",
    "GovernanceService",
    "InMemoryGovernance",
    "raiseForDecision",
]
