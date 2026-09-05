"""Embedding foundation port interfaces for Phase 13-Q.

Minimal contracts the application layer depends on:

- ``VectorSpaceStore`` — persistence of tenant-scoped vector space
  definitions;
- ``EmbeddingStore`` — persistence and retrieval of stored vectors,
  including the fingerprint cache lookup and the brute-force candidate
  scan the foundation ranks in memory;
- ``EmbeddingUsageRecorder`` / ``EmbeddingAuditLogger`` — narrow views of
  the Phase 13-N and Phase 13-O application services. Q depends on these
  two methods only, so the metering and audit layers stay swappable and
  the pure tests need no Django.

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from apps.ai.domain.entities.embeddingRecords import (
    AIStoredEmbedding,
    AIVectorSpaceDefinition,
)


class VectorSpaceStore(Protocol):
    """Persistence contract for vector space definitions."""

    def saveSpace(self, definition: AIVectorSpaceDefinition) -> AIVectorSpaceDefinition: ...
    def getSpace(self, tenantId: UUID, spaceCode: str) -> AIVectorSpaceDefinition | None: ...
    def listSpaces(self, tenantId: UUID) -> tuple[AIVectorSpaceDefinition, ...]: ...
    def updateSpace(self, definition: AIVectorSpaceDefinition) -> AIVectorSpaceDefinition: ...


class EmbeddingStore(Protocol):
    """Persistence contract for stored vectors."""

    def saveEmbedding(self, embedding: AIStoredEmbedding) -> AIStoredEmbedding: ...
    def saveMany(
        self, embeddings: tuple[AIStoredEmbedding, ...]
    ) -> tuple[AIStoredEmbedding, ...]: ...
    def getEmbedding(self, tenantId: UUID, embeddingId: UUID) -> AIStoredEmbedding | None: ...
    def findByFingerprints(
        self, tenantId: UUID, spaceCode: str, fingerprints: tuple[str, ...]
    ) -> tuple[AIStoredEmbedding, ...]: ...
    def listBySource(
        self, tenantId: UUID, spaceCode: str, sourceType: str, sourceId: str
    ) -> tuple[AIStoredEmbedding, ...]: ...
    def scanCandidates(
        self,
        tenantId: UUID,
        spaceCode: str,
        *,
        sourceTypes: tuple[str, ...] = (),
        limit: int = 1000,
    ) -> tuple[AIStoredEmbedding, ...]: ...
    def deleteBySource(
        self, tenantId: UUID, spaceCode: str, sourceType: str, sourceId: str
    ) -> int: ...
    def deleteSpaceEmbeddings(self, tenantId: UUID, spaceCode: str) -> int: ...
    def deleteEmbeddingsBefore(self, tenantId: UUID | None, cutoff: datetime) -> int: ...
    def countForSpace(self, tenantId: UUID, spaceCode: str) -> int: ...


class EmbeddingUsageRecorder(Protocol):
    """The single Phase 13-N entry point Q needs (one metered attempt).

    The signature lists exactly what Q sends, so the real
    ``UsageApplicationService`` (which accepts these plus optional extras)
    satisfies the protocol structurally, without Q importing it.
    """

    def recordProviderAttempt(self, tenantId: Any, command: Any) -> Any: ...


class EmbeddingAuditLogger(Protocol):
    """The single Phase 13-O entry point Q needs (one ledger append)."""

    def logAudit(
        self,
        tenantId: Any,
        action: str,
        *,
        outcome: str = ...,
        modelCode: str = ...,
        providerCode: str = ...,
        requestId: Any = ...,
        correlationId: str = ...,
        traceId: str = ...,
        detail: dict[str, Any] | None = ...,
    ) -> Any: ...


__all__ = [
    "EmbeddingAuditLogger",
    "EmbeddingStore",
    "EmbeddingUsageRecorder",
    "VectorSpaceStore",
]
