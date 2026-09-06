"""Application orchestration for the Phase 13-T memory platform.

``MemoryApplicationService`` implements the five properties §17 demands of
AI memory, each as a real mechanism rather than a claim:

- **Tenant-aware** — every read, write, and purge is tenant-scoped;
- **User-aware** — an entry may belong to a user or to the whole tenant,
  and a user-owned entry is invisible to other principals;
- **Permission-aware** — ``buildContextSources`` runs memory through the
  Phase 13-K filter, so memory enters a prompt through exactly the same
  authorized path as knowledge (§20). With no filter wired, nothing is
  authorized;
- **Versioned** — writes never edit; they supersede and create the next
  version, and the history stays queryable;
- **Auditable** — write, recall, forget, and eviction each append a
  Phase 13-O ledger entry carrying counts and keys, never values.

The service owns no versioning or budget rule itself: both live in
``apps.ai.domain.services.memoryEngine``.

Boundary reminder (§17): AI memory is **not** a second business database.
Entries hold references, summaries, and preferences; the owning domain
stays the source of truth.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.memoryRecords import AIMemoryEntry
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIMemoryInvalid,
    AIMemoryNotFound,
    AIMemoryPolicyInvalid,
)
from apps.ai.domain.memoryPorts import (
    MemoryAuditLogger,
    MemoryEntryStore,
    MemoryPermissionFilter,
)
from apps.ai.domain.services.contextEngine import ContextSourceCandidate
from apps.ai.domain.services.memoryEngine import (
    MemorySelection,
    MemorySelector,
    MemoryWriter,
    RetentionEvaluator,
    RetentionPlan,
)
from apps.ai.domain.valueObjects.memoryTypes import (
    MemoryBudget,
    MemoryKey,
    ScopeBudget,
    ensureMemoryScope,
)

#: Audit actions appended by T (registered in the Phase 13-O vocabulary).
AUDIT_MEMORY_WRITTEN = "MEMORY_WRITTEN"
AUDIT_MEMORY_RECALLED = "MEMORY_RECALLED"
AUDIT_MEMORY_FORGOTTEN = "MEMORY_FORGOTTEN"
AUDIT_MEMORY_EVICTED = "MEMORY_EVICTED"

#: The context source domain every memory block is published under.
MEMORY_SOURCE_DOMAIN = "MEMORY"


@dataclass(frozen=True)
class MemorySettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    maxEntriesPerScope: int = 200
    defaultTtlSeconds: int = 0
    maxValueBytes: int = 32_768
    eviction: str = "OLDEST_FIRST"
    contextMaxEntries: int = 10
    contextMaxTokens: int = 1000
    retentionDays: int = 365
    usePlatformScopeDefaults: bool = True

    def __post_init__(self) -> None:
        if self.contextMaxEntries < 1 or self.contextMaxTokens < 1:
            raise AIConfigurationError("Memory context limits must be positive.")
        if self.retentionDays < 1:
            raise AIConfigurationError("aiMemoryRetentionDays must be positive.")
        # Building the budget here means an impossible configuration fails
        # at construction, not on the first write.
        self.budget()

    def budget(self) -> MemoryBudget:
        """Per-scope budgets: platform defaults narrowed by configuration."""

        override = ScopeBudget(
            maxEntries=self.maxEntriesPerScope,
            ttlSeconds=self.defaultTtlSeconds,
            maxValueBytes=self.maxValueBytes,
            eviction=self.eviction,
        )
        if not self.usePlatformScopeDefaults:
            return MemoryBudget(default=override)
        platform = MemoryBudget.platformDefault()
        narrowed = {
            scope: ScopeBudget(
                maxEntries=min(budget.maxEntries, override.maxEntries),
                ttlSeconds=(
                    budget.ttlSeconds
                    if override.ttlSeconds == 0
                    else min(budget.ttlSeconds or override.ttlSeconds, override.ttlSeconds)
                ),
                maxValueBytes=min(budget.maxValueBytes, override.maxValueBytes),
                eviction=override.eviction,
            )
            for scope, budget in platform.scopes.items()
        }
        return MemoryBudget(scopes=narrowed, default=override)

    @classmethod
    def fromDjangoSettings(cls) -> MemorySettings:
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_MEMORY_ENABLED", True)),
            maxEntriesPerScope=int(
                getattr(djangoSettings, "AI_MEMORY_MAX_ENTRIES_PER_SCOPE", 200) or 200
            ),
            defaultTtlSeconds=int(getattr(djangoSettings, "AI_MEMORY_DEFAULT_TTL_SECONDS", 0) or 0),
            maxValueBytes=int(
                getattr(djangoSettings, "AI_MEMORY_MAX_VALUE_BYTES", 32_768) or 32_768
            ),
            eviction=str(
                getattr(djangoSettings, "AI_MEMORY_EVICTION", "OLDEST_FIRST") or "OLDEST_FIRST"
            ),
            contextMaxEntries=int(
                getattr(djangoSettings, "AI_MEMORY_CONTEXT_MAX_ENTRIES", 10) or 10
            ),
            contextMaxTokens=int(
                getattr(djangoSettings, "AI_MEMORY_CONTEXT_MAX_TOKENS", 1000) or 1000
            ),
            retentionDays=int(getattr(djangoSettings, "AI_MEMORY_RETENTION_DAYS", 365) or 365),
            usePlatformScopeDefaults=bool(
                getattr(djangoSettings, "AI_MEMORY_USE_SCOPE_DEFAULTS", True)
            ),
        )


@dataclass(frozen=True)
class RememberCommand:
    """Write one value into one memory slot (§T.5)."""

    scope: str
    key: str
    value: Any
    kind: str = "FACT"
    userId: uuid.UUID | None = None
    conversationId: str = ""
    classification: str = "INTERNAL"
    expiresAt: datetime | None = None
    sourceReference: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    force: bool = False


@dataclass(frozen=True)
class MemoryDescriptor:
    """Safe read model of one memory version."""

    memoryId: uuid.UUID
    tenantId: uuid.UUID
    scope: str
    key: str
    qualifiedKey: str
    kind: str
    classification: str
    version: int
    isActive: bool
    userId: uuid.UUID | None
    conversationId: str
    sizeBytes: int
    checksum: str
    expiresAt: datetime | None
    supersededAt: datetime | None
    createdAt: datetime

    @classmethod
    def of(cls, entry: AIMemoryEntry) -> MemoryDescriptor:
        return cls(
            memoryId=entry.id,
            tenantId=entry.tenantId,
            scope=entry.scope,
            key=entry.key,
            qualifiedKey=entry.qualifiedKey,
            kind=entry.kind,
            classification=entry.classification,
            version=entry.version,
            isActive=entry.isActive,
            userId=entry.userId,
            conversationId=entry.conversationId,
            sizeBytes=entry.sizeBytes,
            checksum=entry.checksum,
            expiresAt=entry.expiresAt,
            supersededAt=entry.supersededAt,
            createdAt=entry.createdAt,
        )


@dataclass(frozen=True)
class RememberResult:
    """Outcome of one write, including what retention did alongside it."""

    action: str
    reason: str
    memory: MemoryDescriptor
    supersededVersion: int | None = None
    expiredCount: int = 0
    evictedCount: int = 0

    @property
    def isNoop(self) -> bool:
        return self.action == "UNCHANGED"


@dataclass(frozen=True)
class MemoryContextResult:
    """Authorized memory blocks ready to join a prompt (§T.9)."""

    sources: tuple[ContextSourceCandidate, ...]
    entries: tuple[MemoryDescriptor, ...]
    tokenCount: int
    consideredCount: int
    authorizedCount: int
    deniedCount: int

    @property
    def isEmpty(self) -> bool:
        return not self.sources


class MemoryApplicationService:
    """Tenant-scoped facade for remembering, recalling, and forgetting."""

    def __init__(
        self,
        store: MemoryEntryStore,
        *,
        permissionFilter: MemoryPermissionFilter | None = None,
        settings: MemorySettings | None = None,
        auditLogger: MemoryAuditLogger | None = None,
        writer: MemoryWriter | None = None,
        retention: RetentionEvaluator | None = None,
        selector: MemorySelector | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.store = store
        self.permissionFilter = permissionFilter
        self.settings = settings or MemorySettings()
        self.auditLogger = auditLogger
        self.writer = writer or MemoryWriter(now=now)
        self.retention = retention or RetentionEvaluator()
        self.selector = selector or MemorySelector()
        self._now = now

    # ------------------------------------------------------------------
    # Writing (§T.5–§T.6)
    # ------------------------------------------------------------------
    def remember(self, tenantId: uuid.UUID | str, command: RememberCommand) -> RememberResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, RememberCommand):
            raise AIMemoryInvalid("Remembering requires a RememberCommand.")
        memoryKey = MemoryKey(scope=command.scope, key=command.key)
        budget = self.settings.budget().forScope(memoryKey.scope)
        owner = None if command.userId is None else requireUuid(command.userId, "userId")

        latest = self.store.latestForKey(tenant, memoryKey.scope, memoryKey.key, userId=owner)
        plan = self.writer.plan(
            tenant,
            memoryKey,
            command.value,
            latest=latest,
            budget=budget,
            kind=command.kind,
            userId=owner,
            conversationId=command.conversationId,
            classification=command.classification,
            expiresAt=command.expiresAt,
            sourceReference=command.sourceReference,
            metadata=command.metadata,
            force=command.force,
        )
        if plan.isNoop:
            return RememberResult(
                action=plan.action,
                reason=plan.reason,
                memory=MemoryDescriptor.of(plan.entry),
            )

        retentionPlan = self._enforceRetention(tenant, memoryKey.scope, owner, budget, incoming=1)
        if plan.superseded is not None:
            plan.superseded.supersede(now=self._now())
            self.store.updateEntry(plan.superseded)
        stored = self.store.saveEntry(plan.entry)

        self._audit(
            tenant,
            AUDIT_MEMORY_WRITTEN,
            outcome="RECORDED",
            classification=stored.classification,
            actorId=owner,
            contextSources=(stored.qualifiedKey,),
            detail={
                "action": plan.action,
                "scope": stored.scope,
                "key": stored.key,
                "version": stored.version,
                "sizeBytes": stored.sizeBytes,
                "expired": len(retentionPlan.expired),
                "evicted": len(retentionPlan.evicted),
            },
        )
        return RememberResult(
            action=plan.action,
            reason=plan.reason,
            memory=MemoryDescriptor.of(stored),
            supersededVersion=None if plan.superseded is None else plan.superseded.version,
            expiredCount=len(retentionPlan.expired),
            evictedCount=len(retentionPlan.evicted),
        )

    # ------------------------------------------------------------------
    # Reading (§T.7)
    # ------------------------------------------------------------------
    def recall(
        self,
        tenantId: uuid.UUID | str,
        scope: str,
        key: str,
        *,
        userId: uuid.UUID | str | None = None,
        audit: bool = True,
    ) -> Any:
        """Return the current value of one slot, or raise if it has none."""

        entry = self.recallEntry(tenantId, scope, key, userId=userId, audit=audit)
        return entry.value

    def recallEntry(
        self,
        tenantId: uuid.UUID | str,
        scope: str,
        key: str,
        *,
        userId: uuid.UUID | str | None = None,
        audit: bool = True,
    ) -> AIMemoryEntry:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        memoryKey = MemoryKey(scope=scope, key=key)
        owner = None if userId is None else requireUuid(userId, "userId")
        entry = self.store.latestForKey(tenant, memoryKey.scope, memoryKey.key, userId=owner)
        if entry is None or not entry.isUsableAt(self._now()):
            raise AIMemoryNotFound(memoryKey.qualified())
        if not entry.isOwnedBy(owner):
            raise AIMemoryNotFound(memoryKey.qualified())
        if audit:
            self._audit(
                tenant,
                AUDIT_MEMORY_RECALLED,
                outcome="ALLOWED",
                classification=entry.classification,
                actorId=owner,
                contextSources=(entry.qualifiedKey,),
                detail={"scope": entry.scope, "key": entry.key, "version": entry.version},
            )
        return entry

    def describeMemory(
        self, tenantId: uuid.UUID | str, memoryId: uuid.UUID | str
    ) -> MemoryDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        entry = self.store.getEntry(tenant, requireUuid(memoryId, "memoryId"))
        if entry is None:
            raise AIMemoryNotFound(str(memoryId))
        return MemoryDescriptor.of(entry)

    def listMemories(
        self,
        tenantId: uuid.UUID | str,
        *,
        scopes: tuple[str, ...] = (),
        userId: uuid.UUID | str | None = None,
        conversationId: str = "",
        limit: int = 200,
    ) -> tuple[MemoryDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        owner = None if userId is None else requireUuid(userId, "userId")
        normalized = tuple(ensureMemoryScope(scope) for scope in scopes)
        entries = self.store.listActive(
            tenant,
            scopes=normalized,
            userId=owner,
            conversationId=conversationId,
            limit=limit,
        )
        moment = self._now()
        usable = [entry for entry in entries if entry.isUsableAt(moment)]
        return tuple(MemoryDescriptor.of(entry) for entry in usable)

    def history(
        self,
        tenantId: uuid.UUID | str,
        scope: str,
        key: str,
        *,
        userId: uuid.UUID | str | None = None,
    ) -> tuple[MemoryDescriptor, ...]:
        """Every version of one slot, oldest first — memory is auditable."""

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        memoryKey = MemoryKey(scope=scope, key=key)
        owner = None if userId is None else requireUuid(userId, "userId")
        versions = self.store.listVersions(tenant, memoryKey.scope, memoryKey.key, userId=owner)
        return tuple(MemoryDescriptor.of(entry) for entry in versions)

    # ------------------------------------------------------------------
    # Context participation (§T.9)
    # ------------------------------------------------------------------
    def buildContextSources(
        self,
        tenantId: uuid.UUID | str,
        principal: Any,
        *,
        scopes: tuple[str, ...] = (),
        conversationId: str = "",
        maxEntries: int | None = None,
        maxTokens: int | None = None,
    ) -> MemoryContextResult:
        """Select memories and run them through the Phase 13-K filter.

        Memory reaches a prompt only through this method, and only after
        the same fail-closed permission filter that guards knowledge. With
        no filter wired, the result is empty rather than permissive.
        """

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if principal is None:
            raise AIMemoryInvalid("Building memory context requires a principal.")
        principalTenant = getattr(principal, "tenantId", None)
        if principalTenant is not None and requireUuid(principalTenant, "tenantId") != tenant:
            raise AIMemoryInvalid("Principal belongs to another tenant.")
        owner = getattr(principal, "subjectId", None)

        entries = self.store.listActive(
            tenant,
            scopes=tuple(ensureMemoryScope(scope) for scope in scopes),
            userId=None,
            conversationId=conversationId,
            limit=max(1, (maxEntries or self.settings.contextMaxEntries) * 20),
        )
        selection: MemorySelection = self.selector.select(
            entries,
            scopes=scopes,
            maxEntries=maxEntries or self.settings.contextMaxEntries,
            maxTokens=maxTokens or self.settings.contextMaxTokens,
            now=self._now(),
            userId=owner,
        )
        if not selection.entries:
            return MemoryContextResult(
                sources=(),
                entries=(),
                tokenCount=0,
                consideredCount=selection.consideredCount,
                authorizedCount=0,
                deniedCount=0,
            )
        if self.permissionFilter is None:
            raise AIConfigurationError(
                "Memory context requires a permission filter; refusing to expose memory."
            )
        candidates = tuple(
            ContextSourceCandidate(tenantId=tenant, **entry.toContextSource())
            for entry in selection.entries
        )
        verdict = self.permissionFilter.filterSources(principal, candidates)
        authorized = tuple(getattr(verdict, "authorizedSources", ()) or ())
        allowedKeys = {(source.sourceEntityType, source.sourceEntityId) for source in authorized}
        chosen = tuple(
            entry for entry in selection.entries if (entry.scope, entry.key) in allowedKeys
        )
        tokenCount = sum(len(entry.renderedValue()) // 4 + 1 for entry in chosen)
        self._audit(
            tenant,
            AUDIT_MEMORY_RECALLED,
            outcome="ALLOWED" if chosen else "DENIED",
            actorId=owner,
            contextSources=tuple(entry.qualifiedKey for entry in chosen),
            detail={
                "considered": selection.consideredCount,
                "authorized": len(chosen),
                "denied": len(selection.entries) - len(chosen),
            },
        )
        return MemoryContextResult(
            sources=authorized,
            entries=tuple(MemoryDescriptor.of(entry) for entry in chosen),
            tokenCount=tokenCount,
            consideredCount=selection.consideredCount,
            authorizedCount=len(chosen),
            deniedCount=len(selection.entries) - len(chosen),
        )

    # ------------------------------------------------------------------
    # Forgetting and retention (§T.10)
    # ------------------------------------------------------------------
    def forget(
        self,
        tenantId: uuid.UUID | str,
        scope: str,
        key: str,
        *,
        userId: uuid.UUID | str | None = None,
        hard: bool = False,
    ) -> int:
        """Retire a slot. ``hard=True`` deletes every version outright."""

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        memoryKey = MemoryKey(scope=scope, key=key)
        owner = None if userId is None else requireUuid(userId, "userId")
        versions = self.store.listVersions(tenant, memoryKey.scope, memoryKey.key, userId=owner)
        if not versions:
            raise AIMemoryNotFound(memoryKey.qualified())
        if hard:
            affected = self.store.deleteKey(tenant, memoryKey.scope, memoryKey.key, userId=owner)
        else:
            moment = self._now()
            affected = 0
            for entry in versions:
                if not entry.isActive:
                    continue
                entry.forget(now=moment)
                self.store.updateEntry(entry)
                affected += 1
        self._audit(
            tenant,
            AUDIT_MEMORY_FORGOTTEN,
            outcome="PURGED",
            actorId=owner,
            contextSources=(memoryKey.qualified(),),
            detail={
                "scope": memoryKey.scope,
                "key": memoryKey.key,
                "versions": affected,
                "hard": hard,
            },
        )
        return affected

    def enforceRetention(
        self,
        tenantId: uuid.UUID | str,
        *,
        scopes: tuple[str, ...] = (),
        userId: uuid.UUID | str | None = None,
    ) -> dict[str, RetentionPlan]:
        """Apply every scope budget now instead of waiting for a write."""

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        owner = None if userId is None else requireUuid(userId, "userId")
        budget = self.settings.budget()
        targets = tuple(ensureMemoryScope(scope) for scope in scopes) or tuple(
            sorted({entry.scope for entry in self.store.listActive(tenant, limit=1000)})
        )
        plans: dict[str, RetentionPlan] = {}
        for scope in targets:
            plans[scope] = self._enforceRetention(
                tenant, scope, owner, budget.forScope(scope), incoming=0
            )
        return plans

    def purgeMemoryRetention(
        self,
        tenantId: uuid.UUID | str | None = None,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> int:
        """Delete superseded/forgotten versions older than the horizon."""

        self._requireEnabled()
        tenant = None if tenantId is None else requireUuid(tenantId, "tenantId")
        days = self.settings.retentionDays if retentionDays is None else int(retentionDays)
        if days < 1:
            raise AIConfigurationError("Memory retention must be at least one day.")
        cutoff = (now or self._now()) - timedelta(days=days)
        removed = self.store.deleteEntriesBefore(tenant, cutoff)
        if removed and tenant is not None:
            self._audit(
                tenant,
                AUDIT_MEMORY_EVICTED,
                outcome="PURGED",
                detail={"removed": removed, "retentionDays": days},
            )
        return removed

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _enforceRetention(
        self,
        tenant: uuid.UUID,
        scope: str,
        owner: uuid.UUID | None,
        budget: ScopeBudget,
        *,
        incoming: int,
    ) -> RetentionPlan:
        entries = self.store.listActive(
            tenant, scopes=(scope,), userId=owner, limit=budget.maxEntries * 4
        )
        plan = self.retention.evaluate(scope, entries, budget, now=self._now(), incoming=incoming)
        moment = self._now()
        for entry in plan.expired:
            entry.forget(now=moment)
            self.store.updateEntry(entry)
        for entry in plan.evicted:
            entry.forget(now=moment)
            self.store.updateEntry(entry)
        if plan.evicted:
            self._audit(
                tenant,
                AUDIT_MEMORY_EVICTED,
                outcome="PURGED",
                actorId=owner,
                contextSources=tuple(entry.qualifiedKey for entry in plan.evicted),
                detail={
                    "scope": scope,
                    "evicted": len(plan.evicted),
                    "expired": len(plan.expired),
                    "maxEntries": budget.maxEntries,
                },
            )
        return plan

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI memory platform is disabled.")

    def _audit(self, tenant: uuid.UUID, action: str, **kwargs: Any) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(tenant, action, **kwargs)


class MemoryMaintenanceJobHandler:
    """Phase 13-P handler for scheduled memory upkeep (§T.12).

    Payload contract::

        {"scopes": ["SHORT_TERM"], "retentionDays": 365, "purge": true}

    Both steps are idempotent: enforcing a budget that is already met and
    purging a horizon with nothing behind it are no-ops.
    """

    JOB_KIND = "GENERIC"

    def __init__(self, service: MemoryApplicationService) -> None:
        self.service = service

    def kind(self) -> str:
        return self.JOB_KIND

    def execute(self, job: Any) -> Any:
        from apps.ai.domain.services.jobQueue import JobOutcome

        payload = dict(getattr(job, "payload", {}) or {})
        rawScopes = payload.get("scopes", [])
        if not isinstance(rawScopes, list):
            raise AIMemoryPolicyInvalid("Memory maintenance scopes must be a list.")
        scopes = tuple(str(scope) for scope in rawScopes)
        plans = self.service.enforceRetention(job.tenantId, scopes=scopes)
        purged = 0
        if bool(payload.get("purge", False)):
            purged = self.service.purgeMemoryRetention(
                job.tenantId, retentionDays=payload.get("retentionDays")
            )
        return JobOutcome(
            outcome="SUCCEEDED",
            summary={
                "scopes": sorted(plans),
                "expired": sum(len(plan.expired) for plan in plans.values()),
                "evicted": sum(len(plan.evicted) for plan in plans.values()),
                "purged": purged,
            },
        )


__all__ = [
    "AUDIT_MEMORY_EVICTED",
    "AUDIT_MEMORY_FORGOTTEN",
    "AUDIT_MEMORY_RECALLED",
    "AUDIT_MEMORY_WRITTEN",
    "MEMORY_SOURCE_DOMAIN",
    "MemoryApplicationService",
    "MemoryContextResult",
    "MemoryDescriptor",
    "MemoryMaintenanceJobHandler",
    "MemorySettings",
    "RememberCommand",
    "RememberResult",
]
