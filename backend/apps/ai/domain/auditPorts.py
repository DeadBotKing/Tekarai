"""Persistence and retention ports for Phase 13-O audit and governance.

These ``Protocol`` contracts are the only boundary the application layer
uses to store audit entries and governance policies and to purge expired
rows. They are pure Python: no Django, ORM, queue, network, or vendor
dependency.

The ledger is append-only by construction: ``AuditRecordStore`` exposes
no update operation, and the only deletion path is the policy-driven
``RetentionPurger`` whose purges are themselves audited (contract §O.9).
``RetentionPurger`` also owns the sub-phase N tables (attempts/counters)
so the N sources stay untouched; retention of N rows was deferred to O
by the Phase 13-N contract.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Protocol, runtime_checkable

from apps.ai.domain.entities.auditRecords import AIAuditEntry, AIGovernancePolicy
from apps.ai.domain.services.auditTrail import AuditEntryFilter


@runtime_checkable
class AuditRecordStore(Protocol):
    """Persistence boundary for the append-only audit ledger."""

    def appendEntry(self, entry: AIAuditEntry) -> AIAuditEntry: ...
    def getEntry(self, tenantId: uuid.UUID, entryId: uuid.UUID) -> AIAuditEntry: ...
    def listEntries(
        self, tenantId: uuid.UUID, entryFilter: AuditEntryFilter | None = ...
    ) -> tuple[AIAuditEntry, ...]: ...
    def latestHash(self, tenantId: uuid.UUID) -> str: ...
    def deleteBefore(self, tenantId: uuid.UUID, cutoff: datetime) -> int: ...


@runtime_checkable
class GovernancePolicyStore(Protocol):
    """Persistence boundary for the one-policy-per-tenant governance registry."""

    def savePolicy(self, policy: AIGovernancePolicy) -> AIGovernancePolicy: ...
    def getPolicy(self, tenantId: uuid.UUID) -> AIGovernancePolicy: ...
    def updatePolicy(self, policy: AIGovernancePolicy) -> AIGovernancePolicy: ...
    def setPolicyActive(self, tenantId: uuid.UUID, isActive: bool) -> AIGovernancePolicy: ...


@runtime_checkable
class RetentionPurger(Protocol):
    """Policy-driven deletion boundary (§46).

    Implementations delete in one filtered statement per table and return
    exact deleted-row counts. Audit references use plain UUID columns
    (no foreign keys), so purging referenced rows never cascades.
    """

    def purgeAuditBefore(self, tenantId: uuid.UUID, cutoff: datetime) -> int: ...
    def purgeAttemptsBefore(self, tenantId: uuid.UUID, cutoff: datetime) -> int: ...
    def purgeCountersBefore(self, tenantId: uuid.UUID, cutoff: datetime) -> int: ...


__all__ = [
    "AuditRecordStore",
    "GovernancePolicyStore",
    "RetentionPurger",
]
