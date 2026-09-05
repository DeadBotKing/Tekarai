"""Django persistence for Phase 13-O audit and governance ports.

Row↔entity mapping only — no business rule lives here. Every read is
tenant-scoped (a foreign identifier behaves as not-found), the audit
ledger is append-only (no update path exists), and the chain head is
recomputed from the database inside the append transaction, so the store
stays the chain authority even for unhydrated callers.

Retention purges (including the sub-phase N attempt/counter tables) run
as single filtered statements and return exact deleted-row counts; audit
references are plain UUID columns with no foreign keys, so purging
referenced rows never cascades into the ledger.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError, transaction

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.auditRecords import AIAuditEntry, AIGovernancePolicy
from apps.ai.domain.exceptions import (
    AIAuditRecordNotFound,
    AIGovernancePolicyAlreadyRegistered,
    AIGovernancePolicyNotFound,
)
from apps.ai.domain.services.auditTrail import AuditEntryFilter, auditEntryHash
from apps.ai.domain.valueObjects.auditTypes import GENESIS_HASH
from apps.ai.domain.valueObjects.usageTypes import asUtc
from apps.ai.infrastructure.models import (
    AIAuditTrailModel,
    AIGovernancePolicyModel,
    AIQuotaCounterModel,
    AIUsageAttemptModel,
)


def _rebaseSurvivorChain(tenantId: uuid.UUID) -> None:
    """Re-chain surviving entries after a retention purge (§O.9).

    The oldest survivor becomes the new genesis and every later hash is
    recomputed forward in one transaction, so strict genesis-anchored
    verification keeps holding. Hashes are chain-relative by design; the
    ``RETENTION_PURGED`` meta record (appended afterwards by the
    application) documents the sanctioned rebase.
    """

    survivors = list(
        AIAuditTrailModel.objects.filter(tenantId=tenantId).order_by("occurredAt", "id")
    )
    prevHash = GENESIS_HASH
    for row in survivors:
        entry = auditToEntity(row)
        entry.prevHash = prevHash
        entry.hash = auditEntryHash(tenantId, prevHash, entry)
        row.prevHash = prevHash
        row.hash = entry.hash
        row.save(update_fields=["prevHash", "hash"])
        prevHash = entry.hash


def auditToEntity(row: AIAuditTrailModel) -> AIAuditEntry:
    return AIAuditEntry(
        tenantId=row.tenantId,
        action=row.action,
        occurredAt=row.occurredAt,
        id=row.id,
        actorType=row.actorType,
        actorId=row.actorId,
        requestId=row.requestId,
        attemptId=row.attemptId,
        policyId=row.policyId,
        capabilityCode=row.capabilityCode,
        providerCode=row.providerCode,
        modelCode=row.modelCode,
        promptVersion=row.promptVersion,
        classification=row.classification,
        outcome=row.outcome,
        errorCode=row.errorCode,
        correlationId=row.correlationId,
        traceId=row.traceId,
        contextSources=tuple(row.contextSources or []),
        detail=dict(row.detail or {}),
        prevHash=row.prevHash,
        hash=row.hash,
    )


def governancePolicyToEntity(row: AIGovernancePolicyModel) -> AIGovernancePolicy:
    return AIGovernancePolicy(
        tenantId=row.tenantId,
        id=row.id,
        name=row.name,
        allowedProviders=tuple(row.allowedProviders or []),
        allowedModels=tuple(row.allowedModels or []),
        disabledCapabilities=tuple(row.disabledCapabilities or []),
        allowRestrictedToExternal=row.allowRestrictedToExternal,
        maxCostPerDay=row.maxCostPerDay,
        currency=row.currency,
        description=row.description,
        isActive=row.isActive,
        createdAt=row.createdAt,
        updatedAt=row.updatedAt,
    )


class DjangoAuditRecordStore:
    """``AuditRecordStore`` over the ``aiAuditTrail`` table (append-only)."""

    def appendEntry(self, entry: AIAuditEntry) -> AIAuditEntry:
        if not isinstance(entry, AIAuditEntry):
            raise ValueError("Audit store requires an AIAuditEntry.")
        with transaction.atomic():
            rows = list(
                AIAuditTrailModel.objects.filter(tenantId=entry.tenantId).order_by(
                    "occurredAt", "id"
                )
            )
            claimed = {row.prevHash for row in rows}
            tips = [row for row in rows if row.hash and row.hash not in claimed] or rows
            prevHash = tips[-1].hash if tips else GENESIS_HASH
            entry.prevHash = prevHash
            entry.hash = auditEntryHash(entry.tenantId, prevHash, entry)
            row = AIAuditTrailModel.objects.create(
                id=entry.id,
                tenantId=entry.tenantId,
                occurredAt=entry.occurredAt,
                actorType=entry.actorType,
                actorId=entry.actorId,
                action=entry.action,
                requestId=entry.requestId,
                attemptId=entry.attemptId,
                policyId=entry.policyId,
                capabilityCode=entry.capabilityCode,
                providerCode=entry.providerCode,
                modelCode=entry.modelCode,
                promptVersion=entry.promptVersion,
                classification=entry.classification,
                outcome=entry.outcome,
                errorCode=entry.errorCode,
                correlationId=entry.correlationId,
                traceId=entry.traceId,
                contextSources=list(entry.contextSources),
                detail=dict(entry.detail),
                prevHash=entry.prevHash,
                hash=entry.hash,
            )
            return auditToEntity(row)

    def getEntry(self, tenantId: uuid.UUID, entryId: uuid.UUID) -> AIAuditEntry:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(entryId, "entryId")
        try:
            row = AIAuditTrailModel.objects.get(tenantId=tenant, id=identifier)
        except AIAuditTrailModel.DoesNotExist as exc:
            raise AIAuditRecordNotFound(str(identifier)) from exc
        return auditToEntity(row)

    def listEntries(
        self,
        tenantId: uuid.UUID,
        entryFilter: AuditEntryFilter | None = None,
    ) -> tuple[AIAuditEntry, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        active = entryFilter or AuditEntryFilter()
        queryset = AIAuditTrailModel.objects.filter(tenantId=tenant)
        if active.action:
            queryset = queryset.filter(action=str(active.action).strip().upper())
        if active.actorId is not None:
            queryset = queryset.filter(actorId=requireUuid(active.actorId, "actorId"))
        if active.requestId is not None:
            queryset = queryset.filter(requestId=requireUuid(active.requestId, "requestId"))
        if active.outcome:
            queryset = queryset.filter(outcome=str(active.outcome).strip().upper())
        if active.since is not None:
            queryset = queryset.filter(occurredAt__gte=asUtc(active.since))
        if active.until is not None:
            queryset = queryset.filter(occurredAt__lt=asUtc(active.until))
        return tuple(auditToEntity(row) for row in queryset.order_by("occurredAt", "id"))

    def latestHash(self, tenantId: uuid.UUID) -> str:
        tenant = requireUuid(tenantId, "tenantId")
        rows = list(AIAuditTrailModel.objects.filter(tenantId=tenant).order_by("occurredAt", "id"))
        claimed = {row.prevHash for row in rows}
        tips = [row for row in rows if row.hash and row.hash not in claimed] or rows
        return tips[-1].hash if tips else GENESIS_HASH

    def deleteBefore(self, tenantId: uuid.UUID, cutoff: datetime) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        with transaction.atomic():
            deleted, _ = AIAuditTrailModel.objects.filter(
                tenantId=tenant, occurredAt__lt=asUtc(cutoff)
            ).delete()
            _rebaseSurvivorChain(tenant)
        return int(deleted)


class DjangoGovernancePolicyStore:
    """``GovernancePolicyStore`` over the ``aiGovernancePolicies`` table."""

    def savePolicy(self, policy: AIGovernancePolicy) -> AIGovernancePolicy:
        if not isinstance(policy, AIGovernancePolicy):
            raise ValueError("Governance store requires an AIGovernancePolicy.")
        try:
            with transaction.atomic():
                row = AIGovernancePolicyModel.objects.create(
                    id=policy.id,
                    tenantId=policy.tenantId,
                    name=policy.name,
                    allowedProviders=list(policy.allowedProviders),
                    allowedModels=list(policy.allowedModels),
                    disabledCapabilities=list(policy.disabledCapabilities),
                    allowRestrictedToExternal=policy.allowRestrictedToExternal,
                    maxCostPerDay=policy.maxCostPerDay,
                    currency=policy.currency,
                    description=policy.description,
                    isActive=policy.isActive,
                )
        except IntegrityError as exc:
            raise AIGovernancePolicyAlreadyRegistered(
                "A governance policy is already defined for this tenant."
            ) from exc
        return governancePolicyToEntity(row)

    def getPolicy(self, tenantId: uuid.UUID) -> AIGovernancePolicy:
        tenant = requireUuid(tenantId, "tenantId")
        try:
            row = AIGovernancePolicyModel.objects.get(tenantId=tenant)
        except AIGovernancePolicyModel.DoesNotExist as exc:
            raise AIGovernancePolicyNotFound(
                "No governance policy is defined for this tenant."
            ) from exc
        return governancePolicyToEntity(row)

    def updatePolicy(self, policy: AIGovernancePolicy) -> AIGovernancePolicy:
        if not isinstance(policy, AIGovernancePolicy):
            raise ValueError("Governance store requires an AIGovernancePolicy.")
        try:
            row = AIGovernancePolicyModel.objects.get(tenantId=policy.tenantId, id=policy.id)
        except AIGovernancePolicyModel.DoesNotExist as exc:
            raise AIGovernancePolicyNotFound(
                "No governance policy is defined for this tenant."
            ) from exc
        row.name = policy.name
        row.allowedProviders = list(policy.allowedProviders)
        row.allowedModels = list(policy.allowedModels)
        row.disabledCapabilities = list(policy.disabledCapabilities)
        row.allowRestrictedToExternal = policy.allowRestrictedToExternal
        row.maxCostPerDay = policy.maxCostPerDay
        row.currency = policy.currency
        row.description = policy.description
        row.isActive = policy.isActive
        row.save()
        return governancePolicyToEntity(row)

    def setPolicyActive(self, tenantId: uuid.UUID, isActive: bool) -> AIGovernancePolicy:
        policy = self.getPolicy(tenantId)
        if policy.isActive == bool(isActive):
            return policy
        if bool(isActive):
            policy.activate()
        else:
            policy.deactivate()
        AIGovernancePolicyModel.objects.filter(tenantId=policy.tenantId, id=policy.id).update(
            isActive=policy.isActive
        )
        return self.getPolicy(tenantId)


class DjangoRetentionPurger:
    """``RetentionPurger`` over the audit trail and the N metering tables."""

    def purgeAuditBefore(self, tenantId: uuid.UUID, cutoff: datetime) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        with transaction.atomic():
            deleted, _ = AIAuditTrailModel.objects.filter(
                tenantId=tenant, occurredAt__lt=asUtc(cutoff)
            ).delete()
            _rebaseSurvivorChain(tenant)
        return int(deleted)

    def purgeAttemptsBefore(self, tenantId: uuid.UUID, cutoff: datetime) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        deleted, _ = AIUsageAttemptModel.objects.filter(
            tenantId=tenant, createdAt__lt=asUtc(cutoff)
        ).delete()
        return int(deleted)

    def purgeCountersBefore(self, tenantId: uuid.UUID, cutoff: datetime) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        deleted, _ = AIQuotaCounterModel.objects.filter(
            tenantId=tenant, windowStart__lt=asUtc(cutoff)
        ).delete()
        return int(deleted)


__all__ = [
    "DjangoAuditRecordStore",
    "DjangoGovernancePolicyStore",
    "DjangoRetentionPurger",
    "auditToEntity",
    "governancePolicyToEntity",
]
