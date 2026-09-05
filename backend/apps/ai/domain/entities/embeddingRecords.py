"""Embedding foundation entities for Phase 13-Q.

Two records complete the vector side of the AI platform:

- ``AIVectorSpaceDefinition`` — the tenant-scoped registration of a
  ``VectorSpace`` (which model produces it, whether it is open for
  writes). Spaces are declared before use so R/S always know which index
  they are querying and a model swap can never silently mix vectors;
- ``AIStoredEmbedding`` — one durable vector plus the reference to the
  business row it describes. AI never owns the source content: only the
  ``sourceType``/``sourceId`` reference, the content fingerprint, and the
  vector are stored (§Q.3, Master Specification §37).

Both records are pure dataclasses: no Django, ORM, HTTP, provider SDK,
queue, or network dependency. ``AIStoredEmbedding.toDomainEmbedding``
bridges to the Phase 13-B ``AIEmbedding`` primitive so earlier consumers
keep working unchanged.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import AIEmbedding, newId, requireUuid, utcNow
from apps.ai.domain.valueObjects.embeddingTypes import (
    VectorSpace,
    contentFingerprint,
    ensureSourceType,
    isUnitVector,
    validateVector,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")

#: References are opaque strings (a UUID, a business code, a composite key
#: of an owning domain) — AI must not assume the owner's identifier shape.
MAX_SOURCE_ID_LENGTH = 160


def ensureFingerprint(value: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _FINGERPRINT_PATTERN.fullmatch(normalized):
        raise ValidationFailedError(
            "Embedding fingerprint must be a SHA-256 hex digest.",
            fieldErrors={"contentHash": normalized[:16]},
        )
    return normalized


def ensureSourceId(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValidationFailedError("Embedding sourceId is required.")
    if len(normalized) > MAX_SOURCE_ID_LENGTH:
        raise ValidationFailedError(
            "Embedding sourceId is too long.", fieldErrors={"length": str(len(normalized))}
        )
    return normalized


@dataclass
class AIVectorSpaceDefinition:
    """Tenant-scoped registration of one vector space (§Q.5)."""

    tenantId: uuid.UUID
    space: VectorSpace
    modelId: uuid.UUID | None = None
    providerCode: str = ""
    description: str = ""
    isActive: bool = True
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        if not isinstance(self.space, VectorSpace):
            raise ValidationFailedError("A vector space definition requires a VectorSpace.")
        if self.modelId is not None:
            self.modelId = requireUuid(self.modelId, "modelId")
        self.providerCode = str(self.providerCode or "").strip().upper()
        self.description = str(self.description or "").strip()
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Vector space metadata must be a mapping.")

    @property
    def code(self) -> str:
        return self.space.code

    def deactivate(self, *, now: datetime | None = None) -> None:
        """Close the space for writes. Reads stay legal (§Q.5.4)."""

        self.isActive = False
        self.updatedAt = now or utcNow()

    def activate(self, *, now: datetime | None = None) -> None:
        self.isActive = True
        self.updatedAt = now or utcNow()

    def requireWritable(self) -> None:
        if not self.isActive:
            raise ValidationFailedError(
                "Vector space is inactive and cannot accept new embeddings.",
                fieldErrors={"spaceCode": self.space.code},
            )


@dataclass
class AIStoredEmbedding:
    """One durable vector bound to a business reference (§Q.4)."""

    tenantId: uuid.UUID
    space: VectorSpace
    sourceType: str
    sourceId: str
    vector: tuple[float, ...]
    contentHash: str
    chunkId: uuid.UUID | None = None
    modelId: uuid.UUID | None = None
    providerCode: str = ""
    tokenCount: int = 0
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        if not isinstance(self.space, VectorSpace):
            raise ValidationFailedError("A stored embedding requires a VectorSpace.")
        self.sourceType = ensureSourceType(self.sourceType)
        self.sourceId = ensureSourceId(self.sourceId)
        self.contentHash = ensureFingerprint(self.contentHash)
        if self.chunkId is not None:
            self.chunkId = requireUuid(self.chunkId, "chunkId")
        if self.modelId is not None:
            self.modelId = requireUuid(self.modelId, "modelId")
        self.providerCode = str(self.providerCode or "").strip().upper()
        if not isinstance(self.tokenCount, int) or isinstance(self.tokenCount, bool):
            raise ValidationFailedError("Embedding tokenCount must be an integer.")
        if self.tokenCount < 0:
            raise ValidationFailedError("Embedding tokenCount cannot be negative.")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Embedding metadata must be a mapping.")
        self.vector = validateVector(self.vector, dimensions=self.space.dimensions)
        if self.space.isNormalized and not isUnitVector(self.vector):
            raise ValidationFailedError(
                "Vector space declares L2 normalization but the vector is not unit length.",
                fieldErrors={"spaceCode": self.space.code},
            )

    @property
    def dimensions(self) -> int:
        return len(self.vector)

    def belongsTo(self, tenantId: uuid.UUID | str) -> bool:
        return self.tenantId == requireUuid(tenantId, "tenantId")

    def sameSpaceAs(self, space: VectorSpace) -> bool:
        return self.space.matches(space)

    def matchesContent(self, text: str) -> bool:
        """True when ``text`` produces this row's fingerprint in this space."""

        return contentFingerprint(text, self.space) == self.contentHash

    def score(self, queryVector: tuple[float, ...]) -> float:
        """Similarity against a query vector of the *same* space."""

        return self.space.score(self.vector, queryVector)

    def toDomainEmbedding(self) -> AIEmbedding:
        """Bridge to the Phase 13-B ``AIEmbedding`` primitive.

        ``AIEmbedding`` requires a concrete ``modelId``; rows recorded
        without one (offline/deterministic fixtures) cannot be bridged, and
        saying so loudly beats inventing an identifier.
        """

        if self.modelId is None:
            raise ValidationFailedError(
                "A stored embedding without modelId cannot be bridged to AIEmbedding."
            )
        return AIEmbedding(
            tenantId=self.tenantId,
            sourceType=self.sourceType,
            sourceId=self.sourceId,
            modelId=self.modelId,
            vector=self.vector,
            chunkId=self.chunkId,
            id=self.id,
            dimensions=self.dimensions,
            createdAt=self.createdAt,
        )


__all__ = [
    "MAX_SOURCE_ID_LENGTH",
    "AIStoredEmbedding",
    "AIVectorSpaceDefinition",
    "ensureFingerprint",
    "ensureSourceId",
]
