"""Application orchestration for Phase 13-O audit and governance (Django-aware).

``AuditApplicationService`` wires the pure domain coordinators
(``AuditTrailService``, ``GovernanceService``) to the persistence ports,
the retention purger, and the configuration-driven platform defaults
(§42). It owns no business rule itself: chaining, scrubbing, rule order,
and budget math all delegate to the domain layer.

Persistence split (same as Phase 13-G/N):

- governance evaluation (``evaluateGovernance``) persists its decision
  audit before returning — a decision without a record is a violation;
- ``logAudit``/``logQuotaDenial``/``ingestUsageRecorded`` scrub first,
  then append exactly once;
- retention purges delete in one filtered statement per table and then
  append their own ``RETENTION_PURGED`` meta record, so the meta record
  can never be removed by the purge it reports;
- reads hydrate transient domain services from the stores on every call,
  so no cross-request in-memory state exists at this layer.

Concurrency note: evaluation and decision-append are separate store
calls (documented limitation for the sub-phase P worker serialization;
the chain verifier detects forks instead of losing them).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.auditPorts import AuditRecordStore, GovernancePolicyStore, RetentionPurger
from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.auditRecords import (
    AIAuditEntry,
    AIGovernancePolicy,
    GovernanceDecision,
    GovernanceRequest,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIGovernancePolicyNotFound,
)
from apps.ai.domain.meteringPorts import UsageEventSink
from apps.ai.domain.services.auditTrail import (
    AuditEntryDescriptor,
    AuditEntryFilter,
    AuditTrailService,
    scrubDetail,
)
from apps.ai.domain.services.governance import (
    GovernanceEvaluation,
    GovernancePolicyDescriptor,
    GovernanceService,
    raiseForDecision,
)
from apps.ai.domain.services.quotaEnforcement import PolicyDenial
from apps.ai.domain.services.usageMetering import AIUsageRecorded
from apps.ai.domain.valueObjects.aiTypes import Money
from apps.ai.domain.valueObjects.usageTypes import asUtc


@dataclass(frozen=True)
class AuditSettings:
    """Configuration-driven audit/governance defaults (§42 — never hardcoded)."""

    enabled: bool = True
    retentionDays: int = 365
    usageRetentionDays: int = 90
    includeRestrictedDetail: bool = False
    governanceEnabled: bool = True
    defaultMaxCostPerDay: Money = Money(Decimal("0"), "USD")

    def __post_init__(self) -> None:
        if self.retentionDays < 1 or self.usageRetentionDays < 1:
            raise ValueError("Audit retention days must be positive.")

    @classmethod
    def fromDjangoSettings(cls) -> AuditSettings:
        currency = str(getattr(djangoSettings, "AI_GOVERNANCE_DEFAULT_CURRENCY", "USD") or "USD")
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_AUDIT_ENABLED", True)),
            retentionDays=int(getattr(djangoSettings, "AI_AUDIT_RETENTION_DAYS", 365) or 365),
            usageRetentionDays=int(getattr(djangoSettings, "AI_USAGE_RETENTION_DAYS", 90) or 90),
            includeRestrictedDetail=bool(
                getattr(djangoSettings, "AI_AUDIT_INCLUDE_RESTRICTED_DETAIL", False)
            ),
            governanceEnabled=bool(getattr(djangoSettings, "AI_GOVERNANCE_ENABLED", True)),
            defaultMaxCostPerDay=Money(
                Decimal(
                    str(
                        getattr(djangoSettings, "AI_GOVERNANCE_DEFAULT_MAX_COST_PER_DAY", "0")
                        or "0"
                    )
                ),
                currency,
            ),
        )


@dataclass(frozen=True)
class GovernancePolicyCommand:
    """Tenant governance policy definition (§48)."""

    name: str = "default"
    allowedProviders: tuple[str, ...] = ()
    allowedModels: tuple[str, ...] = ()
    disabledCapabilities: tuple[str, ...] = ()
    allowRestrictedToExternal: bool = False
    maxCostPerDay: Decimal | int | str = Decimal("0")
    currency: str = "USD"
    description: str = ""


@dataclass(frozen=True)
class GovernanceGrant:
    tenantId: uuid.UUID
    decision: GovernanceDecision
    auditId: uuid.UUID


@dataclass(frozen=True)
class PurgedRetention:
    tenantId: uuid.UUID
    purgedAt: datetime
    auditDeleted: int
    attemptsDeleted: int
    countersDeleted: int
    auditId: uuid.UUID


class AuditApplicationService:
    """Tenant-scoped application facade for audit and governance."""

    def __init__(
        self,
        auditStore: AuditRecordStore,
        policyStore: GovernancePolicyStore,
        purger: RetentionPurger,
        *,
        auditSettings: AuditSettings | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.auditStore = auditStore
        self.policyStore = policyStore
        self.purger = purger
        self.auditSettings = auditSettings or AuditSettings.fromDjangoSettings()
        self._now = now

    # ------------------------------------------------------------------
    # Governance policy administration (Z exposes it)
    # ------------------------------------------------------------------
    def defineGovernancePolicy(
        self,
        tenantId: uuid.UUID | str,
        command: GovernancePolicyCommand,
        *,
        actorType: str = "SYSTEM",
        actorId: uuid.UUID | str | None = None,
    ) -> AIGovernancePolicy:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireGovernanceEnabled()
        if not isinstance(command, GovernancePolicyCommand):
            raise ValueError("Policy definition requires a GovernancePolicyCommand.")
        governance = GovernanceService(now=self._now)
        policy = governance.definePolicy(
            tenant,
            name=command.name,
            allowedProviders=command.allowedProviders,
            allowedModels=command.allowedModels,
            disabledCapabilities=command.disabledCapabilities,
            allowRestrictedToExternal=command.allowRestrictedToExternal,
            maxCostPerDay=command.maxCostPerDay,
            currency=command.currency,
            description=command.description,
        )
        stored = self.policyStore.savePolicy(policy)
        self._appendPolicyAudit(stored, "GOVERNANCE_POLICY_DEFINED", "DEFINED", actorType, actorId)
        return stored

    def updateGovernancePolicy(
        self,
        tenantId: uuid.UUID | str,
        *,
        actorType: str = "SYSTEM",
        actorId: uuid.UUID | str | None = None,
        now: datetime | None = None,
        **fields: Any,
    ) -> AIGovernancePolicy:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireGovernanceEnabled()
        governance = self._hydratedGovernance(tenant)
        updated = governance.updatePolicy(tenant, now=now or self._now(), **fields)
        stored = self.policyStore.updatePolicy(updated)
        self._appendPolicyAudit(stored, "GOVERNANCE_POLICY_UPDATED", "UPDATED", actorType, actorId)
        return stored

    def deactivateGovernancePolicy(
        self,
        tenantId: uuid.UUID | str,
        *,
        actorType: str = "SYSTEM",
        actorId: uuid.UUID | str | None = None,
    ) -> AIGovernancePolicy:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireGovernanceEnabled()
        governance = self._hydratedGovernance(tenant)
        governance.deactivatePolicy(tenant, now=self._now())
        stored = self.policyStore.setPolicyActive(tenant, False)
        self._appendPolicyAudit(stored, "GOVERNANCE_POLICY_UPDATED", "UPDATED", actorType, actorId)
        return stored

    def describeGovernancePolicy(self, tenantId: uuid.UUID | str) -> GovernancePolicyDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        governance = self._hydratedGovernance(tenant)
        try:
            return governance.describePolicy(tenant)
        except AIGovernancePolicyNotFound:
            platform = self._platformDefaultPolicy(tenant)
            governance.importPolicy(platform)
            return governance.describePolicy(tenant)

    # ------------------------------------------------------------------
    # Governance evaluation (every decision is audited)
    # ------------------------------------------------------------------
    def evaluateGovernance(
        self,
        request: GovernanceRequest,
        *,
        now: datetime | None = None,
    ) -> GovernanceGrant:
        self._requireGovernanceEnabled()
        self._requireAuditEnabled()
        if not isinstance(request, GovernanceRequest):
            raise ValueError("Governance evaluation requires a GovernanceRequest.")
        tenant = request.tenantId
        governance = self._hydratedGovernance(tenant)
        try:
            policy = governance.getPolicy(tenant)
            policySource = "tenant"
        except AIGovernancePolicyNotFound:
            policy = self._platformDefaultPolicy(tenant)
            governance.importPolicy(policy)
            policySource = "platform-default"
        evaluation: GovernanceEvaluation = governance.evaluate(request, policy, now=now)
        decision = GovernanceDecision(
            tenantId=evaluation.tenantId,
            allowed=evaluation.allowed,
            reasons=evaluation.reasons,
            evaluatedAt=evaluation.evaluatedAt,
        )
        audit = self._appendDecisionAudit(request, policy, decision, source=policySource)
        if not decision.allowed:
            raiseForDecision(decision)
        return GovernanceGrant(tenantId=tenant, decision=decision, auditId=audit.id)

    # ------------------------------------------------------------------
    # Audit writes
    # ------------------------------------------------------------------
    def logAudit(
        self,
        tenantId: uuid.UUID | str,
        action: str,
        *,
        occurredAt: datetime | None = None,
        actorType: str = "SYSTEM",
        actorId: uuid.UUID | str | None = None,
        requestId: uuid.UUID | str | None = None,
        attemptId: uuid.UUID | str | None = None,
        policyId: uuid.UUID | str | None = None,
        capabilityCode: str = "",
        providerCode: str = "",
        modelCode: str = "",
        promptVersion: str = "",
        classification: str = "INTERNAL",
        outcome: str = "RECORDED",
        errorCode: str = "",
        correlationId: str = "",
        traceId: str = "",
        contextSources: tuple[str, ...] | list[str] | None = None,
        detail: dict[str, Any] | None = None,
        allowRestrictedDetail: bool | None = None,
    ) -> AIAuditEntry:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireAuditEnabled()
        trail = self._hydratedTrail(tenant)
        scrubbed = scrubDetail(
            detail or {},
            classification=classification,
            allowRestrictedDetail=(
                self.auditSettings.includeRestrictedDetail
                if allowRestrictedDetail is None
                else allowRestrictedDetail
            ),
        )
        entry = trail.logEntry(
            tenant,
            action,
            occurredAt=occurredAt or self._now(),
            actorType=actorType,
            actorId=actorId,
            requestId=requestId,
            attemptId=attemptId,
            policyId=policyId,
            capabilityCode=capabilityCode,
            providerCode=providerCode,
            modelCode=modelCode,
            promptVersion=promptVersion,
            classification=classification,
            outcome=outcome,
            errorCode=errorCode,
            correlationId=correlationId,
            traceId=traceId,
            contextSources=contextSources,
            detail=scrubbed if isinstance(scrubbed, dict) else {"value": scrubbed},
        )
        return self.auditStore.appendEntry(entry)

    def logQuotaDenial(
        self,
        tenantId: uuid.UUID | str,
        denial: PolicyDenial,
        *,
        actorType: str = "SYSTEM",
        actorId: uuid.UUID | str | None = None,
        requestId: uuid.UUID | str | None = None,
        correlationId: str = "",
        traceId: str = "",
    ) -> AIAuditEntry:
        tenant = requireUuid(tenantId, "tenantId")
        if not isinstance(denial, PolicyDenial):
            raise ValueError("Quota denial audit requires a PolicyDenial.")
        return self.logAudit(
            tenant,
            "QUOTA_DENIED",
            actorType=actorType,
            actorId=actorId,
            requestId=requestId,
            policyId=denial.policyId,
            outcome="DENIED",
            correlationId=correlationId,
            traceId=traceId,
            detail={
                "scope": denial.scope,
                "dimension": denial.dimension,
                "window": denial.window,
                "windowStart": denial.windowStart.isoformat(),
                "limitValue": str(denial.limitValue),
                "consumed": str(denial.consumed),
            },
        )

    def ingestUsageRecorded(self, event: AIUsageRecorded) -> AIAuditEntry:
        if not isinstance(event, AIUsageRecorded):
            raise ValueError("Usage ingestion requires an AIUsageRecorded carrier.")
        return self.logAudit(
            event.tenantId,
            "USAGE_RECORDED",
            occurredAt=event.recordedAt,
            requestId=event.requestId,
            attemptId=event.attemptId,
            capabilityCode=event.capabilityCode,
            providerCode=event.providerCode,
            modelCode=event.modelCode,
            outcome=event.outcome,
            correlationId=event.correlationId,
            traceId=event.traceId,
            detail={
                "inputTokens": event.inputTokens,
                "outputTokens": event.outputTokens,
                "totalTokens": event.totalTokens,
                "costAmount": str(event.costAmount),
                "costCurrency": event.costCurrency,
                "totalTimeMs": event.totalTimeMs,
            },
        )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    def listAuditEntries(
        self,
        tenantId: uuid.UUID | str,
        entryFilter: AuditEntryFilter | None = None,
    ) -> tuple[AuditEntryDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        trail = self._hydratedTrail(tenant)
        entries = self.auditStore.listEntries(tenant, entryFilter)
        for entry in entries:
            trail.importEntry(entry)
        return tuple(
            trail.describeEntry(tenant, entry.id)
            for entry in trail.listEntries(tenant, entryFilter)
        )

    def verifyTenantChain(self, tenantId: uuid.UUID | str) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        trail = self._hydratedTrail(tenant)
        for entry in self.auditStore.listEntries(tenant):
            trail.importEntry(entry)
        return trail.verifyChain(tenant)

    # ------------------------------------------------------------------
    # Retention (§46 — purges audit and the N tables, then self-reports)
    # ------------------------------------------------------------------
    def purgeAuditRetention(
        self,
        tenantId: uuid.UUID | str,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> PurgedRetention:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireAuditEnabled()
        days = self.auditSettings.retentionDays if retentionDays is None else retentionDays
        trail = AuditTrailService(now=self._now)
        cutoff = trail.retentionCutoff(tenant, days, now=now or self._now()).cutoff
        deleted = self.purger.purgeAuditBefore(tenant, cutoff)
        moment = asUtc(now) if now is not None else self._now()
        meta = self.logAudit(
            tenant,
            "RETENTION_PURGED",
            occurredAt=moment,
            outcome="PURGED",
            detail={
                "table": "aiAuditTrail",
                "retentionDays": days,
                "cutoff": cutoff.isoformat(),
                "deleted": deleted,
            },
        )
        return PurgedRetention(
            tenantId=tenant,
            purgedAt=moment,
            auditDeleted=deleted,
            attemptsDeleted=0,
            countersDeleted=0,
            auditId=meta.id,
        )

    def purgeUsageRetention(
        self,
        tenantId: uuid.UUID | str,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> PurgedRetention:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireAuditEnabled()
        days = self.auditSettings.usageRetentionDays if retentionDays is None else retentionDays
        trail = AuditTrailService(now=self._now)
        cutoff = trail.retentionCutoff(tenant, days, now=now or self._now()).cutoff
        attempts = self.purger.purgeAttemptsBefore(tenant, cutoff)
        counters = self.purger.purgeCountersBefore(tenant, cutoff)
        moment = asUtc(now) if now is not None else self._now()
        meta = self.logAudit(
            tenant,
            "RETENTION_PURGED",
            occurredAt=moment,
            outcome="PURGED",
            detail={
                "tables": ["aiUsageAttempts", "aiQuotaCounters"],
                "retentionDays": days,
                "cutoff": cutoff.isoformat(),
                "attemptsDeleted": attempts,
                "countersDeleted": counters,
            },
        )
        return PurgedRetention(
            tenantId=tenant,
            purgedAt=moment,
            auditDeleted=0,
            attemptsDeleted=attempts,
            countersDeleted=counters,
            auditId=meta.id,
        )

    # ------------------------------------------------------------------
    # Internal orchestration
    # ------------------------------------------------------------------
    def _requireAuditEnabled(self) -> None:
        if not self.auditSettings.enabled:
            raise AIConfigurationError("AI audit is disabled by configuration.")

    def _requireGovernanceEnabled(self) -> None:
        if not self.auditSettings.governanceEnabled:
            raise AIConfigurationError("AI governance is disabled by configuration.")

    def _hydratedTrail(self, tenant: uuid.UUID) -> AuditTrailService:
        trail = AuditTrailService(now=self._now)
        for entry in self.auditStore.listEntries(tenant):
            trail.importEntry(entry)
        return trail

    def _hydratedGovernance(self, tenant: uuid.UUID) -> GovernanceService:
        governance = GovernanceService(now=self._now)
        try:
            governance.importPolicy(self.policyStore.getPolicy(tenant))
        except AIGovernancePolicyNotFound:
            pass
        return governance

    def _platformDefaultPolicy(self, tenant: uuid.UUID) -> AIGovernancePolicy:
        return AIGovernancePolicy(
            tenantId=tenant,
            name="platform-default",
            maxCostPerDay=self.auditSettings.defaultMaxCostPerDay.amount,
            currency=self.auditSettings.defaultMaxCostPerDay.currency,
        )

    def _appendPolicyAudit(
        self,
        policy: AIGovernancePolicy,
        action: str,
        outcome: str,
        actorType: str,
        actorId: uuid.UUID | str | None,
    ) -> AIAuditEntry:
        trail = self._hydratedTrail(policy.tenantId)
        entry = trail.logEntry(
            policy.tenantId,
            action,
            occurredAt=self._now(),
            actorType=actorType,
            actorId=actorId,
            policyId=policy.id,
            outcome=outcome,
            detail={"policyId": str(policy.id), "name": policy.name},
        )
        return self.auditStore.appendEntry(entry)

    def _appendDecisionAudit(
        self,
        request: GovernanceRequest,
        policy: AIGovernancePolicy,
        decision: GovernanceDecision,
        *,
        source: str,
    ) -> AIAuditEntry:
        trail = self._hydratedTrail(request.tenantId)
        entry = trail.logEntry(
            request.tenantId,
            "GOVERNANCE_ALLOW" if decision.allowed else "GOVERNANCE_DENY",
            occurredAt=decision.evaluatedAt,
            actorType=request.actorType,
            actorId=request.actorId,
            requestId=request.requestId,
            policyId=policy.id if source == "tenant" else None,
            capabilityCode=request.capabilityCode,
            providerCode=request.providerCode,
            modelCode=request.modelCode,
            classification=request.classification,
            outcome="ALLOWED" if decision.allowed else "DENIED",
            correlationId=request.correlationId,
            traceId=request.traceId,
            detail={
                "decision": "ALLOW" if decision.allowed else "DENY",
                "policySource": source,
                "policyId": str(policy.id),
                "rules": {
                    "allowedProviders": list(policy.allowedProviders),
                    "allowedModels": list(policy.allowedModels),
                    "disabledCapabilities": list(policy.disabledCapabilities),
                    "allowRestrictedToExternal": policy.allowRestrictedToExternal,
                    "maxCostPerDay": str(policy.maxCostPerDay),
                    "currency": policy.currency,
                },
                "reasons": [
                    {"rule": reason.rule, "allowed": reason.allowed, "message": reason.message}
                    for reason in decision.reasons
                ],
            },
        )
        return self.auditStore.appendEntry(entry)


class AuditUsageEventSink(UsageEventSink):
    """In-process N→O binding: every published usage carrier becomes an audit entry."""

    def __init__(self, auditService: AuditApplicationService) -> None:
        if not isinstance(auditService, AuditApplicationService):
            raise ValueError("Audit event sink requires an AuditApplicationService.")
        self.auditService = auditService

    def publish(self, event: AIUsageRecorded) -> None:
        if not isinstance(event, AIUsageRecorded):
            raise ValueError("Audit event sink requires an AIUsageRecorded carrier.")
        self.auditService.ingestUsageRecorded(event)


AuditTrailApplicationService = AuditApplicationService
AIAuditTrailService = AuditApplicationService

__all__ = [
    "AIAuditTrailService",
    "AuditApplicationService",
    "AuditSettings",
    "AuditTrailApplicationService",
    "AuditUsageEventSink",
    "GovernanceGrant",
    "GovernancePolicyCommand",
    "PurgedRetention",
]
