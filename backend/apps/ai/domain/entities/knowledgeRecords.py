"""Knowledge ingestion entities for Phase 13-R.

Two records complete the knowledge side of the AI platform:

- ``AIKnowledgeSourceRecord`` — the registered, tenant-scoped *reference*
  to a business row that may be indexed (which domain owns it, its content
  checksum, its lifecycle status, which vector space indexes it, and how
  many chunks it currently has). The original content is **not** stored:
  AI keeps reference, index, and metadata only (Master Specification §37);
- ``AIKnowledgeChunkRecord`` — one retrievable unit derived from that
  content, with its own checksum (the unit of incremental reuse), token
  count, character offsets back into the canonical text, and the
  classification inherited from its source.

Chunk text *is* stored, deliberately: it is the retrievable index the RAG
pipeline of S reads, it is always derivable again from the owning domain,
and it is purged whenever the source is archived or deleted (§R.11).

Both records are pure dataclasses with no Django, ORM, HTTP, provider SDK,
queue, or network dependency. ``toDomainChunk`` bridges to the Phase 13-B
``AIKnowledgeChunk`` primitive.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import AIKnowledgeChunk, newId, requireUuid, utcNow
from apps.ai.domain.valueObjects.aiTypes import (
    DATA_CLASSIFICATIONS,
    KNOWLEDGE_STATUSES,
    ensureEnum,
)
from apps.ai.domain.valueObjects.knowledgeTypes import (
    ChunkingPolicy,
    ensureSourceDomain,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

_CHECKSUM_PATTERN = re.compile(r"^[0-9a-f]{64}$")

MAX_ENTITY_ID_LENGTH = 160
MAX_TITLE_LENGTH = 300

#: Lifecycle transitions, identical to the Phase 13-B knowledge machine so
#: two competing state machines can never exist (§R.6).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"INDEXING", "ARCHIVED"},
    "INDEXING": {"READY", "FAILED"},
    "READY": {"INDEXING", "ARCHIVED"},
    "FAILED": {"INDEXING", "ARCHIVED"},
    "ARCHIVED": set(),
}


def ensureChecksum(value: str, fieldName: str = "checksum") -> str:
    normalized = str(value or "").strip().lower()
    if not _CHECKSUM_PATTERN.fullmatch(normalized):
        raise ValidationFailedError(
            "Knowledge checksum must be a SHA-256 hex digest.",
            fieldErrors={fieldName: normalized[:16]},
        )
    return normalized


def ensureEntityId(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValidationFailedError("Knowledge sourceEntityId is required.")
    if len(normalized) > MAX_ENTITY_ID_LENGTH:
        raise ValidationFailedError(
            "Knowledge sourceEntityId is too long.",
            fieldErrors={"length": str(len(normalized))},
        )
    return normalized


def ensureEntityKind(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if not normalized:
        raise ValidationFailedError("Knowledge sourceEntityType is required.")
    if len(normalized) > 100:
        raise ValidationFailedError("Knowledge sourceEntityType is too long.")
    return normalized


@dataclass
class AIKnowledgeSourceRecord:
    """A registered, indexable reference to a business row (§R.4)."""

    tenantId: uuid.UUID
    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    title: str
    checksum: str
    classification: str = "INTERNAL"
    status: str = "PENDING"
    spaceCode: str = ""
    policySignature: str = ""
    revision: int = 0
    chunkCount: int = 0
    tokenCount: int = 0
    lastIndexedAt: datetime | None = None
    errorCode: str = ""
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.sourceDomain = ensureSourceDomain(self.sourceDomain)
        self.sourceEntityType = ensureEntityKind(self.sourceEntityType)
        self.sourceEntityId = ensureEntityId(self.sourceEntityId)
        self.title = str(self.title or "").strip()
        if not self.title:
            raise ValidationFailedError("Knowledge title is required.")
        if len(self.title) > MAX_TITLE_LENGTH:
            raise ValidationFailedError("Knowledge title is too long.")
        self.checksum = ensureChecksum(self.checksum)
        self.classification = ensureEnum(
            self.classification, DATA_CLASSIFICATIONS, "classification"
        )
        self.status = ensureEnum(self.status, KNOWLEDGE_STATUSES, "knowledgeStatus")
        self.spaceCode = str(self.spaceCode or "").strip().upper()
        self.policySignature = str(self.policySignature or "").strip()
        self.errorCode = str(self.errorCode or "").strip().upper()
        for name in ("revision", "chunkCount", "tokenCount"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationFailedError(
                    "Knowledge counters must be non-negative integers.",
                    fieldErrors={name: str(value)},
                )
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Knowledge metadata must be a mapping.")

    # -- identity -------------------------------------------------------
    @property
    def naturalKey(self) -> tuple[str, str, str]:
        """The owning-domain identity: one source per business row."""

        return (self.sourceDomain, self.sourceEntityType, self.sourceEntityId)

    def reference(self) -> str:
        return f"{self.sourceDomain}:{self.sourceEntityType}:{self.sourceEntityId}"

    def hasContentChanged(self, checksum: str) -> bool:
        return ensureChecksum(checksum) != self.checksum

    def matchesPolicy(self, policy: ChunkingPolicy) -> bool:
        return bool(self.policySignature) and self.policySignature == policy.signature()

    # -- lifecycle ------------------------------------------------------
    def transitionTo(self, status: str, *, now: datetime | None = None) -> None:
        target = ensureEnum(status, KNOWLEDGE_STATUSES, "knowledgeStatus")
        if target != self.status and target not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValidationFailedError(
                f"Invalid knowledge transition {self.status} → {target}.",
                fieldErrors={"status": target},
            )
        self.status = target
        self.updatedAt = now or utcNow()

    def markIndexed(
        self,
        *,
        checksum: str,
        chunkCount: int,
        tokenCount: int,
        policy: ChunkingPolicy,
        spaceCode: str = "",
        now: datetime | None = None,
    ) -> None:
        """Close a successful ingestion run and bump the revision."""

        moment = now or utcNow()
        self.transitionTo("READY", now=moment)
        self.checksum = ensureChecksum(checksum)
        if chunkCount < 0 or tokenCount < 0:
            raise ValidationFailedError("Index counters cannot be negative.")
        self.chunkCount = chunkCount
        self.tokenCount = tokenCount
        self.policySignature = policy.signature()
        if spaceCode:
            self.spaceCode = str(spaceCode).strip().upper()
        self.revision += 1
        self.errorCode = ""
        self.lastIndexedAt = moment

    def markFailed(self, errorCode: str, *, now: datetime | None = None) -> None:
        self.transitionTo("FAILED", now=now)
        self.errorCode = str(errorCode or "AI_KNOWLEDGE_INGESTION_FAILED").strip().upper()

    def archive(self, *, now: datetime | None = None) -> None:
        self.transitionTo("ARCHIVED", now=now)
        self.chunkCount = 0
        self.tokenCount = 0

    def requireIngestable(self) -> None:
        if self.status == "ARCHIVED":
            raise ValidationFailedError(
                "An archived knowledge source cannot be re-ingested.",
                fieldErrors={"status": self.status},
            )


@dataclass
class AIKnowledgeChunkRecord:
    """One retrievable unit derived from a source's content (§R.5)."""

    tenantId: uuid.UUID
    sourceId: uuid.UUID
    ordinal: int
    text: str
    checksum: str
    tokenCount: int = 0
    startOffset: int = 0
    endOffset: int = 0
    classification: str = "INTERNAL"
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.sourceId = requireUuid(self.sourceId, "sourceId")
        self.id = requireUuid(self.id, "id")
        self.text = str(self.text or "").strip()
        if not self.text:
            raise ValidationFailedError("Chunk text cannot be empty.")
        self.checksum = ensureChecksum(self.checksum, "chunkChecksum")
        self.classification = ensureEnum(
            self.classification, DATA_CLASSIFICATIONS, "classification"
        )
        for name in ("ordinal", "tokenCount", "startOffset", "endOffset"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationFailedError(
                    "Chunk counters must be non-negative integers.",
                    fieldErrors={name: str(value)},
                )
        if self.endOffset < self.startOffset:
            raise ValidationFailedError("Chunk endOffset cannot precede startOffset.")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Chunk metadata must be a mapping.")

    @property
    def embeddingSourceId(self) -> str:
        """The reference Phase 13-Q stores for this chunk's vector."""

        return str(self.id)

    def reorder(self, ordinal: int) -> None:
        """Move a reused chunk to its new position without re-embedding."""

        if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
            raise ValidationFailedError("Chunk ordinal must be a non-negative integer.")
        self.ordinal = ordinal

    def toDomainChunk(self) -> AIKnowledgeChunk:
        """Bridge to the Phase 13-B ``AIKnowledgeChunk`` primitive."""

        return AIKnowledgeChunk(
            tenantId=self.tenantId,
            itemId=self.sourceId,
            ordinal=self.ordinal,
            content=self.text,
            tokenCount=self.tokenCount,
            id=self.id,
            metadata=dict(self.metadata),
            createdAt=self.createdAt,
        )


__all__ = [
    "MAX_ENTITY_ID_LENGTH",
    "MAX_TITLE_LENGTH",
    "AIKnowledgeChunkRecord",
    "AIKnowledgeSourceRecord",
    "ensureChecksum",
    "ensureEntityId",
    "ensureEntityKind",
]
