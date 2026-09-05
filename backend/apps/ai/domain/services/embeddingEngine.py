"""Pure embedding engine for Phase 13-Q.

Everything here is deterministic, offline, and provider-agnostic:

- ``EmbeddingItem`` — one text plus the business reference it describes.
  The canonical text and its fingerprint are computed at construction, so
  the cache key is decided in the domain and never by a caller;
- ``EmbeddingPlan`` — the outcome of planning a batch: which items are
  already cached, which must be sent, how the pending set is deduplicated
  and split into provider batches, and the estimated token cost;
- ``EmbeddingEngine`` — planning, provider-result validation, and entity
  construction;
- ``SimilarityMatch`` / ``rankBySimilarity`` — deterministic top-K ranking
  with a stable tie-break (§Q.7).

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
It performs **no** authorization: permission filtering is Phase 13-K's
engine, applied by the retrieval pipeline of S before context assembly
(Master Specification §20). Q only guarantees tenant and space integrity.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import newId, requireUuid, utcNow
from apps.ai.domain.entities.embeddingRecords import (
    AIStoredEmbedding,
    ensureSourceId,
)
from apps.ai.domain.exceptions import (
    AIEmbeddingBatchTooLarge,
    AIEmbeddingInvalid,
    AITokenLimitExceeded,
    AIVectorSpaceMismatch,
)
from apps.ai.domain.services.aiRules import estimateTokens
from apps.ai.domain.valueObjects.embeddingTypes import (
    MAX_BATCH_SIZE,
    SCORE_PRECISION,
    VectorSpace,
    contentFingerprint,
    ensureSourceType,
    normalizeText,
)


@dataclass(frozen=True)
class EmbeddingItem:
    """One embeddable text bound to a business reference."""

    text: str
    sourceType: str = "CUSTOM"
    sourceId: str = ""
    chunkId: uuid.UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        canonical = normalizeText(self.text)
        if not canonical:
            raise AIEmbeddingInvalid("Embedding text cannot be empty.")
        object.__setattr__(self, "text", canonical)
        object.__setattr__(self, "sourceType", ensureSourceType(self.sourceType))
        object.__setattr__(self, "sourceId", ensureSourceId(self.sourceId or str(newId())))
        if self.chunkId is not None:
            object.__setattr__(self, "chunkId", requireUuid(self.chunkId, "chunkId"))
        if not isinstance(self.metadata, dict):
            raise AIEmbeddingInvalid("Embedding item metadata must be a mapping.")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def fingerprint(self, space: VectorSpace) -> str:
        return contentFingerprint(self.text, space)

    @property
    def estimatedTokens(self) -> int:
        return estimateTokens(self.text)


@dataclass(frozen=True)
class EmbeddingPlan:
    """Deduplicated, batched, budget-checked work order (§Q.8)."""

    space: VectorSpace
    pending: tuple[EmbeddingItem, ...]
    cached: tuple[EmbeddingItem, ...]
    batches: tuple[tuple[EmbeddingItem, ...], ...]
    duplicates: int
    estimatedTokens: int

    @property
    def providerCalls(self) -> int:
        return len(self.batches)

    @property
    def isEmpty(self) -> bool:
        return not self.pending

    def fingerprints(self) -> tuple[str, ...]:
        return tuple(item.fingerprint(self.space) for item in self.pending)


@dataclass(frozen=True)
class SimilarityMatch:
    """Non-sensitive ranked hit. Content never travels in a match (§Q.7.3)."""

    embeddingId: uuid.UUID
    sourceType: str
    sourceId: str
    score: float
    contentHash: str
    chunkId: uuid.UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def fromEmbedding(cls, embedding: AIStoredEmbedding, score: float) -> SimilarityMatch:
        return cls(
            embeddingId=embedding.id,
            sourceType=embedding.sourceType,
            sourceId=embedding.sourceId,
            score=round(float(score), SCORE_PRECISION),
            contentHash=embedding.contentHash,
            chunkId=embedding.chunkId,
            metadata=dict(embedding.metadata),
        )


def rankBySimilarity(
    space: VectorSpace,
    queryVector: Sequence[float],
    candidates: Iterable[AIStoredEmbedding],
    *,
    topK: int = 10,
    minScore: float | None = None,
) -> tuple[SimilarityMatch, ...]:
    """Rank candidates against a query vector inside one space.

    Deterministic by construction: scores are rounded to
    ``SCORE_PRECISION`` and equal scores break on
    ``(sourceType, sourceId, embeddingId)`` so two runs over the same data
    can never disagree. A candidate from a different space is a hard error,
    not a silently skipped row.
    """

    if topK < 1:
        raise AIEmbeddingInvalid("topK must be positive.")
    prepared = space.prepare(queryVector)
    scored: list[tuple[float, str, str, str, SimilarityMatch]] = []
    for candidate in candidates:
        if not candidate.sameSpaceAs(space):
            raise AIVectorSpaceMismatch("Candidate embedding belongs to a different vector space.")
        score = candidate.score(prepared)
        if minScore is not None and score < minScore:
            continue
        match = SimilarityMatch.fromEmbedding(candidate, score)
        scored.append(
            (-match.score, match.sourceType, match.sourceId, str(match.embeddingId), match)
        )
    scored.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
    return tuple(row[4] for row in scored[:topK])


class EmbeddingEngine:
    """Planning and construction rules for the embedding foundation."""

    def __init__(
        self,
        *,
        maxBatchSize: int = 32,
        maxInputTokens: int = 8192,
        now: Any = utcNow,
    ) -> None:
        if maxBatchSize < 1 or maxBatchSize > MAX_BATCH_SIZE:
            raise AIEmbeddingInvalid("maxBatchSize is out of range.")
        if maxInputTokens < 1:
            raise AIEmbeddingInvalid("maxInputTokens must be positive.")
        self._maxBatchSize = int(maxBatchSize)
        self._maxInputTokens = int(maxInputTokens)
        self._now = now

    @property
    def maxBatchSize(self) -> int:
        return self._maxBatchSize

    @property
    def maxInputTokens(self) -> int:
        return self._maxInputTokens

    # ------------------------------------------------------------------
    # Planning (§Q.8)
    # ------------------------------------------------------------------
    def plan(
        self,
        space: VectorSpace,
        items: Iterable[EmbeddingItem],
        *,
        knownFingerprints: Iterable[str] = (),
        maxItems: int | None = None,
    ) -> EmbeddingPlan:
        """Deduplicate, subtract the cache, budget-check, and batch.

        Order is preserved: the first occurrence of a fingerprint wins, so
        planning is reproducible and callers can zip results back onto
        their inputs.
        """

        if not isinstance(space, VectorSpace):
            raise AIEmbeddingInvalid("Planning requires a VectorSpace.")
        materialized = list(items)
        for item in materialized:
            if not isinstance(item, EmbeddingItem):
                raise AIEmbeddingInvalid("Planning requires EmbeddingItem values.")
        ceiling = self._maxBatchSize if maxItems is None else int(maxItems)
        if maxItems is not None and (ceiling < 1 or ceiling > MAX_BATCH_SIZE):
            raise AIEmbeddingBatchTooLarge("Requested batch ceiling is out of range.")
        if len(materialized) > MAX_BATCH_SIZE:
            raise AIEmbeddingBatchTooLarge("Embedding batch exceeds the absolute platform ceiling.")
        if maxItems is not None and len(materialized) > ceiling:
            raise AIEmbeddingBatchTooLarge("Embedding batch exceeds the configured ceiling.")

        known = {str(value).strip().lower() for value in knownFingerprints}
        seen: set[str] = set()
        pending: list[EmbeddingItem] = []
        cached: list[EmbeddingItem] = []
        duplicates = 0
        for item in materialized:
            if item.estimatedTokens > self._maxInputTokens:
                raise AITokenLimitExceeded("Embedding input exceeds the configured token budget.")
            fingerprint = item.fingerprint(space)
            if fingerprint in known:
                cached.append(item)
                continue
            if fingerprint in seen:
                duplicates += 1
                continue
            seen.add(fingerprint)
            pending.append(item)

        batches = tuple(
            tuple(pending[start : start + self._maxBatchSize])
            for start in range(0, len(pending), self._maxBatchSize)
        )
        return EmbeddingPlan(
            space=space,
            pending=tuple(pending),
            cached=tuple(cached),
            batches=batches,
            duplicates=duplicates,
            estimatedTokens=sum(item.estimatedTokens for item in pending),
        )

    # ------------------------------------------------------------------
    # Construction (§Q.9)
    # ------------------------------------------------------------------
    def buildEmbedding(
        self,
        tenantId: uuid.UUID | str,
        space: VectorSpace,
        item: EmbeddingItem,
        vector: Sequence[float],
        *,
        modelId: uuid.UUID | None = None,
        providerCode: str = "",
        tokenCount: int | None = None,
        embeddingId: uuid.UUID | None = None,
        createdAt: datetime | None = None,
    ) -> AIStoredEmbedding:
        """Validate a provider vector and turn it into a storable entity."""

        tenant = requireUuid(tenantId, "tenantId")
        prepared = space.prepare(vector)
        return AIStoredEmbedding(
            tenantId=tenant,
            space=space,
            sourceType=item.sourceType,
            sourceId=item.sourceId,
            vector=prepared,
            contentHash=item.fingerprint(space),
            chunkId=item.chunkId,
            modelId=modelId,
            providerCode=providerCode,
            tokenCount=item.estimatedTokens if tokenCount is None else int(tokenCount),
            id=embeddingId or newId(),
            metadata=dict(item.metadata),
            createdAt=createdAt or self._now(),
        )

    def buildBatch(
        self,
        tenantId: uuid.UUID | str,
        space: VectorSpace,
        items: Sequence[EmbeddingItem],
        vectors: Sequence[Sequence[float]],
        *,
        modelId: uuid.UUID | None = None,
        providerCode: str = "",
        tokenCounts: Sequence[int] | None = None,
        createdAt: datetime | None = None,
    ) -> tuple[AIStoredEmbedding, ...]:
        """Zip a provider batch response onto its request items.

        A provider that returns a different number of vectors than texts
        has violated the C contract; refusing the whole batch keeps the
        store free of misaligned vectors.
        """

        if len(items) != len(vectors):
            raise AIEmbeddingInvalid("Provider returned a different number of vectors than inputs.")
        if tokenCounts is not None and len(tokenCounts) != len(items):
            raise AIEmbeddingInvalid("Token counts must align with the batch items.")
        moment = createdAt or self._now()
        return tuple(
            self.buildEmbedding(
                tenantId,
                space,
                item,
                vector,
                modelId=modelId,
                providerCode=providerCode,
                tokenCount=None if tokenCounts is None else tokenCounts[index],
                createdAt=moment,
            )
            for index, (item, vector) in enumerate(zip(items, vectors, strict=True))
        )

    def prepareQuery(self, space: VectorSpace, text: str) -> EmbeddingItem:
        """Build the transient ``QUERY`` item for a similarity search."""

        item = EmbeddingItem(text=text, sourceType="QUERY", sourceId="query")
        if item.estimatedTokens > self._maxInputTokens:
            raise AITokenLimitExceeded("Query exceeds the configured token budget.")
        # Touch the space so an invalid space fails before the provider call.
        item.fingerprint(space)
        return item


__all__ = [
    "EmbeddingEngine",
    "EmbeddingItem",
    "EmbeddingPlan",
    "SimilarityMatch",
    "rankBySimilarity",
]
