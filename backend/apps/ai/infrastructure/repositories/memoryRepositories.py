"""Django persistence for the Phase 13-T memory platform.

Row↔entity mapping only — no business rule lives here. Every read and
write is tenant-scoped (a foreign identifier behaves as not-found), and
entities are rehydrated through the domain record so an invalid stored row
can never re-enter the domain unvalidated.

Two details worth stating:

- **Versions are rows, not edits.** ``saveEntry`` only ever inserts;
  ``updateEntry`` exists solely to flip the lifecycle flags
  (``isActive``/``supersededAt``) of a version that has been retired.
- **Owner-scoped lookups.** ``userId=None`` means "tenant-wide entries
  only"; passing an owner returns that user's entries *and* the
  tenant-wide ones, which is what a recall on behalf of a user needs.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db.models import Q

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.memoryRecords import AIMemoryEntry
from apps.ai.domain.exceptions import AIMemoryInvalid
from apps.ai.domain.valueObjects.memoryTypes import MemoryKey, normalizeKey
from apps.ai.infrastructure.models import AIMemoryEntryModel

#: Sentinel written to ``ownerKey`` for tenant-wide slots (§T.8).
TENANT_OWNER_KEY = "tenant"


def ownerKeyFor(userId: uuid.UUID | None) -> str:
    """Non-null owner projection used by the uniqueness constraint."""

    return TENANT_OWNER_KEY if userId is None else str(userId)


def memoryToEntity(row: AIMemoryEntryModel) -> AIMemoryEntry:
    """Map a memory row to its domain record."""

    return AIMemoryEntry(
        tenantId=row.tenantId,
        memoryKey=MemoryKey(scope=row.scope, key=row.memoryKey),
        value=row.value,
        kind=row.kind,
        userId=row.userId,
        conversationId=row.conversationId or "",
        classification=row.classification,
        version=row.version,
        isActive=row.isActive,
        expiresAt=row.expiresAt,
        supersededAt=row.supersededAt,
        sourceReference=row.sourceReference or "",
        checksum=row.checksum,
        sizeBytes=row.sizeBytes,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


class DjangoMemoryEntryStore:
    """``MemoryEntryStore`` over ``aiMemoryEntries``."""

    # -- internals ------------------------------------------------------
    @staticmethod
    def _ownerFilter(query: Q, userId: uuid.UUID | None) -> Q:
        """Tenant-wide rows are always visible; owned rows only to their owner."""

        if userId is None:
            return query & Q(userId__isnull=True)
        return query & (Q(userId=userId) | Q(userId__isnull=True))

    # -- writes ---------------------------------------------------------
    def saveEntry(self, entry: AIMemoryEntry) -> AIMemoryEntry:
        row = AIMemoryEntryModel.objects.create(
            id=entry.id,
            tenantId=entry.tenantId,
            scope=entry.scope,
            memoryKey=entry.key,
            kind=entry.kind,
            userId=entry.userId,
            ownerKey=ownerKeyFor(entry.userId),
            conversationId=entry.conversationId,
            classification=entry.classification,
            value=entry.value,
            checksum=entry.checksum,
            sizeBytes=entry.sizeBytes,
            version=entry.version,
            isActive=entry.isActive,
            expiresAt=entry.expiresAt,
            supersededAt=entry.supersededAt,
            sourceReference=entry.sourceReference,
            metadata=dict(entry.metadata),
        )
        return memoryToEntity(row)

    def updateEntry(self, entry: AIMemoryEntry) -> AIMemoryEntry:
        updated = AIMemoryEntryModel.objects.filter(tenantId=entry.tenantId, id=entry.id).update(
            isActive=entry.isActive,
            supersededAt=entry.supersededAt,
            expiresAt=entry.expiresAt,
            classification=entry.classification,
            metadata=dict(entry.metadata),
        )
        if not updated:
            raise AIMemoryInvalid("Memory row was not found for update.")
        return memoryToEntity(AIMemoryEntryModel.objects.get(tenantId=entry.tenantId, id=entry.id))

    # -- reads ----------------------------------------------------------
    def getEntry(self, tenantId: uuid.UUID, entryId: uuid.UUID) -> AIMemoryEntry | None:
        row = AIMemoryEntryModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id=requireUuid(entryId, "entryId")
        ).first()
        return None if row is None else memoryToEntity(row)

    def latestForKey(
        self,
        tenantId: uuid.UUID,
        scope: str,
        key: str,
        *,
        userId: uuid.UUID | None = None,
    ) -> AIMemoryEntry | None:
        base = Q(
            tenantId=requireUuid(tenantId, "tenantId"),
            scope=str(scope).strip().upper(),
            memoryKey=normalizeKey(key),
        )
        row = (
            AIMemoryEntryModel.objects.filter(self._ownerFilter(base, userId))
            .order_by("-version", "-createdAt")
            .first()
        )
        return None if row is None else memoryToEntity(row)

    def listVersions(
        self,
        tenantId: uuid.UUID,
        scope: str,
        key: str,
        *,
        userId: uuid.UUID | None = None,
    ) -> tuple[AIMemoryEntry, ...]:
        base = Q(
            tenantId=requireUuid(tenantId, "tenantId"),
            scope=str(scope).strip().upper(),
            memoryKey=normalizeKey(key),
        )
        rows = AIMemoryEntryModel.objects.filter(self._ownerFilter(base, userId)).order_by(
            "version", "createdAt"
        )
        return tuple(memoryToEntity(row) for row in rows)

    def listActive(
        self,
        tenantId: uuid.UUID,
        *,
        scopes: tuple[str, ...] = (),
        userId: uuid.UUID | None = None,
        conversationId: str = "",
        limit: int = 500,
    ) -> tuple[AIMemoryEntry, ...]:
        base = Q(tenantId=requireUuid(tenantId, "tenantId"), isActive=True)
        if scopes:
            base &= Q(scope__in=[str(scope).strip().upper() for scope in scopes])
        if conversationId:
            base &= Q(conversationId=str(conversationId).strip())
        query = AIMemoryEntryModel.objects.filter(base)
        if userId is not None:
            query = query.filter(Q(userId=userId) | Q(userId__isnull=True))
        rows = query.order_by("scope", "memoryKey", "-version")[: max(1, int(limit))]
        return tuple(memoryToEntity(row) for row in rows)

    def countActive(
        self, tenantId: uuid.UUID, scope: str, *, userId: uuid.UUID | None = None
    ) -> int:
        base = Q(
            tenantId=requireUuid(tenantId, "tenantId"),
            scope=str(scope).strip().upper(),
            isActive=True,
        )
        query = AIMemoryEntryModel.objects.filter(base)
        if userId is not None:
            query = query.filter(Q(userId=userId) | Q(userId__isnull=True))
        return int(query.count())

    # -- deletes --------------------------------------------------------
    def deleteEntries(self, tenantId: uuid.UUID, entryIds: tuple[uuid.UUID, ...]) -> int:
        if not entryIds:
            return 0
        removed, _ = AIMemoryEntryModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id__in=list(entryIds)
        ).delete()
        return int(removed)

    def deleteKey(
        self, tenantId: uuid.UUID, scope: str, key: str, *, userId: uuid.UUID | None = None
    ) -> int:
        base = Q(
            tenantId=requireUuid(tenantId, "tenantId"),
            scope=str(scope).strip().upper(),
            memoryKey=normalizeKey(key),
        )
        removed, _ = AIMemoryEntryModel.objects.filter(self._ownerFilter(base, userId)).delete()
        return int(removed)

    def deleteEntriesBefore(self, tenantId: uuid.UUID | None, cutoff: datetime) -> int:
        """Purge retired versions only; a live memory is never swept away."""

        query = AIMemoryEntryModel.objects.filter(isActive=False, createdAt__lt=cutoff)
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        removed, _ = query.delete()
        return int(removed)


__all__ = [
    "TENANT_OWNER_KEY",
    "DjangoMemoryEntryStore",
    "memoryToEntity",
    "ownerKeyFor",
]
