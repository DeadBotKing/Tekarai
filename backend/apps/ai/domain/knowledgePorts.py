"""Knowledge ingestion port interfaces for Phase 13-R.

Minimal contracts the application layer depends on:

- ``KnowledgeSourceStore`` — persistence of the tenant-scoped source
  register, including lookup by the owning-domain natural key;
- ``KnowledgeChunkStore`` — persistence of derived chunks, including the
  bulk reorder that makes incremental reindexing cheap;
- ``ChunkEmbedder`` — the two Phase 13-Q entry points R needs. The
  signature matches ``EmbeddingApplicationService`` exactly, so the real
  service satisfies it structurally and R never imports Q's concrete
  class;
- ``KnowledgeAuditLogger`` — the single Phase 13-O ledger append.

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from apps.ai.domain.entities.knowledgeRecords import (
    AIKnowledgeChunkRecord,
    AIKnowledgeSourceRecord,
)


class KnowledgeSourceStore(Protocol):
    """Persistence contract for the knowledge source register."""

    def saveSource(self, source: AIKnowledgeSourceRecord) -> AIKnowledgeSourceRecord: ...
    def updateSource(self, source: AIKnowledgeSourceRecord) -> AIKnowledgeSourceRecord: ...
    def getSource(self, tenantId: UUID, sourceId: UUID) -> AIKnowledgeSourceRecord | None: ...
    def findByNaturalKey(
        self, tenantId: UUID, sourceDomain: str, sourceEntityType: str, sourceEntityId: str
    ) -> AIKnowledgeSourceRecord | None: ...
    def listSources(
        self, tenantId: UUID, *, statuses: tuple[str, ...] = (), sourceDomain: str = ""
    ) -> tuple[AIKnowledgeSourceRecord, ...]: ...
    def deleteSource(self, tenantId: UUID, sourceId: UUID) -> int: ...
    def deleteSourcesBefore(self, tenantId: UUID | None, cutoff: datetime) -> tuple[UUID, ...]: ...


class KnowledgeChunkStore(Protocol):
    """Persistence contract for derived chunks."""

    def saveChunks(
        self, chunks: tuple[AIKnowledgeChunkRecord, ...]
    ) -> tuple[AIKnowledgeChunkRecord, ...]: ...
    def listChunks(self, tenantId: UUID, sourceId: UUID) -> tuple[AIKnowledgeChunkRecord, ...]: ...
    def getChunk(self, tenantId: UUID, chunkId: UUID) -> AIKnowledgeChunkRecord | None: ...
    def reorderChunks(self, tenantId: UUID, ordinals: dict[UUID, int]) -> int: ...
    def reclassifyChunks(self, tenantId: UUID, sourceId: UUID, classification: str) -> int: ...
    def deleteChunks(self, tenantId: UUID, chunkIds: tuple[UUID, ...]) -> int: ...
    def deleteSourceChunks(self, tenantId: UUID, sourceId: UUID) -> int: ...
    def countChunks(self, tenantId: UUID, sourceId: UUID) -> int: ...


class ChunkEmbedder(Protocol):
    """The Phase 13-Q surface R uses to index and unindex chunk vectors."""

    def embedTexts(self, tenantId: Any, command: Any) -> Any: ...
    def deleteSourceEmbeddings(
        self, tenantId: Any, spaceCode: str, sourceType: str, sourceId: str
    ) -> int: ...


class KnowledgeAuditLogger(Protocol):
    """The single Phase 13-O entry point R needs (one ledger append)."""

    def logAudit(
        self,
        tenantId: Any,
        action: str,
        *,
        outcome: str = ...,
        classification: str = ...,
        errorCode: str = ...,
        contextSources: tuple[str, ...] | list[str] | None = ...,
        detail: dict[str, Any] | None = ...,
    ) -> Any: ...


__all__ = [
    "ChunkEmbedder",
    "KnowledgeAuditLogger",
    "KnowledgeChunkStore",
    "KnowledgeSourceStore",
]
