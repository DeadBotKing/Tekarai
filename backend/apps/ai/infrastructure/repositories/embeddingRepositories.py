"""Django persistence for the Phase 13-Q embedding foundation.

Row↔entity mapping only — no business rule lives here. Every read and
write is tenant-scoped and space-scoped (a foreign identifier behaves as
not-found), and vectors are rehydrated through the domain entity so an
invalid stored row can never re-enter the domain unvalidated.

``saveMany`` is idempotent on the ``(tenantId, spaceCode, contentHash)``
cache key: a concurrent writer that already stored the same content wins
and its row is returned, so a race produces one row, never a duplicate or
an ``IntegrityError`` escaping to the caller.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError, transaction

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.embeddingRecords import (
    AIStoredEmbedding,
    AIVectorSpaceDefinition,
)
from apps.ai.domain.exceptions import AIVectorSpaceInvalid
from apps.ai.domain.valueObjects.embeddingTypes import VectorSpace
from apps.ai.infrastructure.models import AIStoredEmbeddingModel, AIVectorSpaceModel


def spaceToEntity(row: AIVectorSpaceModel) -> AIVectorSpaceDefinition:
    """Map a space row to its domain definition."""

    return AIVectorSpaceDefinition(
        tenantId=row.tenantId,
        space=VectorSpace(
            code=row.code,
            modelCode=row.modelCode,
            dimensions=row.dimensions,
            metric=row.metric,
            normalization=row.normalization,
            modelVersion=row.modelVersion or "",
        ),
        modelId=row.modelId,
        providerCode=row.providerCode or "",
        description=row.description or "",
        isActive=row.isActive,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
        updatedAt=row.updatedAt,
    )


def embeddingToEntity(row: AIStoredEmbeddingModel, space: VectorSpace) -> AIStoredEmbedding:
    """Map a vector row to its domain entity inside a resolved space."""

    return AIStoredEmbedding(
        tenantId=row.tenantId,
        space=space,
        sourceType=row.sourceType,
        sourceId=row.sourceId,
        vector=tuple(float(value) for value in (row.vector or [])),
        contentHash=row.contentHash,
        chunkId=row.chunkId,
        modelId=row.modelId,
        providerCode=row.providerCode or "",
        tokenCount=row.tokenCount,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


class DjangoVectorSpaceStore:
    """``VectorSpaceStore`` over ``aiVectorSpaces``."""

    def saveSpace(self, definition: AIVectorSpaceDefinition) -> AIVectorSpaceDefinition:
        space = definition.space
        row = AIVectorSpaceModel.objects.create(
            id=definition.id,
            tenantId=definition.tenantId,
            code=space.code,
            modelCode=space.modelCode,
            modelVersion=space.modelVersion,
            modelId=definition.modelId,
            providerCode=definition.providerCode,
            dimensions=space.dimensions,
            metric=space.metric,
            normalization=space.normalization,
            description=definition.description,
            isActive=definition.isActive,
            metadata=dict(definition.metadata),
        )
        return spaceToEntity(row)

    def getSpace(self, tenantId: uuid.UUID, spaceCode: str) -> AIVectorSpaceDefinition | None:
        tenant = requireUuid(tenantId, "tenantId")
        row = AIVectorSpaceModel.objects.filter(
            tenantId=tenant, code=str(spaceCode or "").strip().upper()
        ).first()
        return None if row is None else spaceToEntity(row)

    def listSpaces(self, tenantId: uuid.UUID) -> tuple[AIVectorSpaceDefinition, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        rows = AIVectorSpaceModel.objects.filter(tenantId=tenant).order_by("code")
        return tuple(spaceToEntity(row) for row in rows)

    def updateSpace(self, definition: AIVectorSpaceDefinition) -> AIVectorSpaceDefinition:
        updated = AIVectorSpaceModel.objects.filter(
            tenantId=definition.tenantId, id=definition.id
        ).update(
            isActive=definition.isActive,
            description=definition.description,
            providerCode=definition.providerCode,
            metadata=dict(definition.metadata),
        )
        if not updated:
            raise AIVectorSpaceInvalid("Vector space row was not found for update.")
        row = AIVectorSpaceModel.objects.get(tenantId=definition.tenantId, id=definition.id)
        return spaceToEntity(row)


class DjangoEmbeddingStore:
    """``EmbeddingStore`` over ``aiEmbeddingVectors``.

    The store resolves each row's space from ``aiVectorSpaces`` so entities
    always carry the authoritative space identity rather than a copy that
    could drift from the registration.
    """

    def __init__(self, spaceStore: DjangoVectorSpaceStore | None = None) -> None:
        self.spaceStore = spaceStore or DjangoVectorSpaceStore()
        self._spaceCache: dict[tuple[uuid.UUID, str], VectorSpace] = {}

    # -- internals ------------------------------------------------------
    def _space(self, tenantId: uuid.UUID, spaceCode: str) -> VectorSpace:
        key = (tenantId, spaceCode)
        cached = self._spaceCache.get(key)
        if cached is not None:
            return cached
        definition = self.spaceStore.getSpace(tenantId, spaceCode)
        if definition is None:
            raise AIVectorSpaceInvalid("Stored embedding references an unknown vector space.")
        self._spaceCache[key] = definition.space
        return definition.space

    def _hydrate(self, rows: object) -> tuple[AIStoredEmbedding, ...]:
        result: list[AIStoredEmbedding] = []
        for row in rows:  # type: ignore[attr-defined]
            result.append(embeddingToEntity(row, self._space(row.tenantId, row.spaceCode)))
        return tuple(result)

    # -- writes ---------------------------------------------------------
    def saveEmbedding(self, embedding: AIStoredEmbedding) -> AIStoredEmbedding:
        try:
            with transaction.atomic():
                row = AIStoredEmbeddingModel.objects.create(
                    id=embedding.id,
                    tenantId=embedding.tenantId,
                    spaceCode=embedding.space.code,
                    sourceType=embedding.sourceType,
                    sourceId=embedding.sourceId,
                    chunkId=embedding.chunkId,
                    modelId=embedding.modelId,
                    providerCode=embedding.providerCode,
                    dimensions=embedding.dimensions,
                    vector=[float(value) for value in embedding.vector],
                    contentHash=embedding.contentHash,
                    tokenCount=embedding.tokenCount,
                    metadata=dict(embedding.metadata),
                )
        except IntegrityError:
            # Cache-key race: the concurrent writer's row is authoritative.
            existing = AIStoredEmbeddingModel.objects.filter(
                tenantId=embedding.tenantId,
                spaceCode=embedding.space.code,
                contentHash=embedding.contentHash,
            ).first()
            if existing is None:
                raise
            return embeddingToEntity(existing, embedding.space)
        return embeddingToEntity(row, embedding.space)

    def saveMany(self, embeddings: tuple[AIStoredEmbedding, ...]) -> tuple[AIStoredEmbedding, ...]:
        return tuple(self.saveEmbedding(embedding) for embedding in embeddings)

    # -- reads ----------------------------------------------------------
    def getEmbedding(self, tenantId: uuid.UUID, embeddingId: uuid.UUID) -> AIStoredEmbedding | None:
        tenant = requireUuid(tenantId, "tenantId")
        row = AIStoredEmbeddingModel.objects.filter(
            tenantId=tenant, id=requireUuid(embeddingId, "embeddingId")
        ).first()
        if row is None:
            return None
        return embeddingToEntity(row, self._space(tenant, row.spaceCode))

    def findByFingerprints(
        self, tenantId: uuid.UUID, spaceCode: str, fingerprints: tuple[str, ...]
    ) -> tuple[AIStoredEmbedding, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        if not fingerprints:
            return ()
        rows = AIStoredEmbeddingModel.objects.filter(
            tenantId=tenant, spaceCode=spaceCode, contentHash__in=list(fingerprints)
        )
        return self._hydrate(rows)

    def listBySource(
        self, tenantId: uuid.UUID, spaceCode: str, sourceType: str, sourceId: str
    ) -> tuple[AIStoredEmbedding, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        rows = AIStoredEmbeddingModel.objects.filter(
            tenantId=tenant, spaceCode=spaceCode, sourceType=sourceType, sourceId=sourceId
        ).order_by("createdAt", "id")
        return self._hydrate(rows)

    def scanCandidates(
        self,
        tenantId: uuid.UUID,
        spaceCode: str,
        *,
        sourceTypes: tuple[str, ...] = (),
        limit: int = 1000,
    ) -> tuple[AIStoredEmbedding, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        query = AIStoredEmbeddingModel.objects.filter(tenantId=tenant, spaceCode=spaceCode)
        if sourceTypes:
            query = query.filter(sourceType__in=list(sourceTypes))
        rows = query.order_by("createdAt", "id")[: max(1, int(limit))]
        return self._hydrate(rows)

    def countForSpace(self, tenantId: uuid.UUID, spaceCode: str) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        return int(
            AIStoredEmbeddingModel.objects.filter(tenantId=tenant, spaceCode=spaceCode).count()
        )

    # -- deletes --------------------------------------------------------
    def deleteBySource(
        self, tenantId: uuid.UUID, spaceCode: str, sourceType: str, sourceId: str
    ) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        removed, _ = AIStoredEmbeddingModel.objects.filter(
            tenantId=tenant, spaceCode=spaceCode, sourceType=sourceType, sourceId=sourceId
        ).delete()
        return int(removed)

    def deleteSpaceEmbeddings(self, tenantId: uuid.UUID, spaceCode: str) -> int:
        tenant = requireUuid(tenantId, "tenantId")
        removed, _ = AIStoredEmbeddingModel.objects.filter(
            tenantId=tenant, spaceCode=spaceCode
        ).delete()
        return int(removed)

    def deleteEmbeddingsBefore(self, tenantId: uuid.UUID | None, cutoff: datetime) -> int:
        query = AIStoredEmbeddingModel.objects.filter(createdAt__lt=cutoff)
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        removed, _ = query.delete()
        return int(removed)


__all__ = [
    "DjangoEmbeddingStore",
    "DjangoVectorSpaceStore",
    "embeddingToEntity",
    "spaceToEntity",
]
