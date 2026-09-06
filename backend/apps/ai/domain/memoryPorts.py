"""AI memory port interfaces for Phase 13-T.

Minimal contracts the application layer depends on:

- ``MemoryEntryStore`` — persistence of memory versions, including the
  "latest usable version of one slot" lookup that every write and recall
  starts from;
- ``MemoryPermissionFilter`` — the Phase 13-K fail-closed filter, used so
  memory reaches a prompt through the same authorized path as knowledge;
- ``MemoryAuditLogger`` — the single Phase 13-O ledger append.

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from apps.ai.domain.entities.memoryRecords import AIMemoryEntry


class MemoryEntryStore(Protocol):
    """Persistence contract for versioned memory entries."""

    def saveEntry(self, entry: AIMemoryEntry) -> AIMemoryEntry: ...
    def updateEntry(self, entry: AIMemoryEntry) -> AIMemoryEntry: ...
    def getEntry(self, tenantId: UUID, entryId: UUID) -> AIMemoryEntry | None: ...
    def latestForKey(
        self, tenantId: UUID, scope: str, key: str, *, userId: UUID | None = None
    ) -> AIMemoryEntry | None: ...
    def listVersions(
        self, tenantId: UUID, scope: str, key: str, *, userId: UUID | None = None
    ) -> tuple[AIMemoryEntry, ...]: ...
    def listActive(
        self,
        tenantId: UUID,
        *,
        scopes: tuple[str, ...] = (),
        userId: UUID | None = None,
        conversationId: str = "",
        limit: int = 500,
    ) -> tuple[AIMemoryEntry, ...]: ...
    def countActive(self, tenantId: UUID, scope: str, *, userId: UUID | None = None) -> int: ...
    def deleteEntries(self, tenantId: UUID, entryIds: tuple[UUID, ...]) -> int: ...
    def deleteKey(
        self, tenantId: UUID, scope: str, key: str, *, userId: UUID | None = None
    ) -> int: ...
    def deleteEntriesBefore(self, tenantId: UUID | None, cutoff: datetime) -> int: ...


class MemoryPermissionFilter(Protocol):
    """Phase 13-K: the fail-closed permission boundary."""

    def filterSources(
        self, principal: Any, sources: Any, *, action: Any = ..., now: Any = ...
    ) -> Any: ...


class MemoryAuditLogger(Protocol):
    """The single Phase 13-O entry point T needs (one ledger append)."""

    def logAudit(
        self,
        tenantId: Any,
        action: str,
        *,
        outcome: str = ...,
        classification: str = ...,
        actorId: Any = ...,
        contextSources: tuple[str, ...] | list[str] | None = ...,
        detail: dict[str, Any] | None = ...,
    ) -> Any: ...


__all__ = [
    "MemoryAuditLogger",
    "MemoryEntryStore",
    "MemoryPermissionFilter",
]
