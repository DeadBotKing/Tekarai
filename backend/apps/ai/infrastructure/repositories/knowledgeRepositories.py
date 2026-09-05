"""Django persistence for the Phase 13-R knowledge platform.

Row↔entity mapping only — no business rule lives here. Every read and write
is tenant-scoped (a foreign identifier behaves as not-found), and entities
are rehydrated through the domain records so an invalid stored row can never
re-enter the domain unvalidated.

``reorderChunks`` is the incremental-reindex primitive: it moves reused
chunks to their new positions in one pass. Ordinals are written through a
two-phase shift (offset by a constant, then to the target) so a swap of two
positions cannot collide even under a future unique constraint on
``(source, ordinal)``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import transaction

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.knowledgeRecords import (
    AIKnowledgeChunkRecord,
    AIKnowledgeSourceRecord,
)
from apps.ai.domain.exceptions import AIKnowledgeSourceInvalid
from apps.ai.infrastructure.models import (
    AIKnowledgeChunkRecordModel,
    AIKnowledgeSourceModel,
)

#: Temporary offset used by the two-phase ordinal shift.
_ORDINAL_SHIFT = 1_000_000


def sourceToEntity(row: AIKnowledgeSourceModel) -> AIKnowledgeSourceRecord:
    """Map a register row to its domain record."""

    return AIKnowledgeSourceRecord(
        tenantId=row.tenantId,
        sourceDomain=row.sourceDomain,
        sourceEntityType=row.sourceEntityType,
        sourceEntityId=row.sourceEntityId,
        title=row.title,
        checksum=row.checksum,
        classification=row.classification,
        status=row.status,
        spaceCode=row.spaceCode or "",
        policySignature=row.policySignature or "",
        revision=row.revision,
        chunkCount=row.chunkCount,
        tokenCount=row.tokenCount,
        lastIndexedAt=row.lastIndexedAt,
        errorCode=row.errorCode or "",
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
        updatedAt=row.updatedAt,
    )


def chunkToEntity(row: AIKnowledgeChunkRecordModel) -> AIKnowledgeChunkRecord:
    """Map a chunk row to its domain record."""

    return AIKnowledgeChunkRecord(
        tenantId=row.tenantId,
        sourceId=row.source_id,
        ordinal=row.ordinal,
        text=row.text,
        checksum=row.checksum,
        tokenCount=row.tokenCount,
        startOffset=row.startOffset,
        endOffset=row.endOffset,
        classification=row.classification,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


class DjangoKnowledgeSourceStore:
    """``KnowledgeSourceStore`` over ``aiKnowledgeSources``."""

    def saveSource(self, source: AIKnowledgeSourceRecord) -> AIKnowledgeSourceRecord:
        row = AIKnowledgeSourceModel.objects.create(
            id=source.id,
            tenantId=source.tenantId,
            sourceDomain=source.sourceDomain,
            sourceEntityType=source.sourceEntityType,
            sourceEntityId=source.sourceEntityId,
            title=source.title,
            checksum=source.checksum,
            classification=source.classification,
            status=source.status,
            spaceCode=source.spaceCode,
            policySignature=source.policySignature,
            revision=source.revision,
            chunkCount=source.chunkCount,
            tokenCount=source.tokenCount,
            errorCode=source.errorCode,
            lastIndexedAt=source.lastIndexedAt,
            metadata=dict(source.metadata),
        )
        return sourceToEntity(row)

    def updateSource(self, source: AIKnowledgeSourceRecord) -> AIKnowledgeSourceRecord:
        updated = AIKnowledgeSourceModel.objects.filter(
            tenantId=source.tenantId, id=source.id
        ).update(
            title=source.title,
            checksum=source.checksum,
            classification=source.classification,
            status=source.status,
            spaceCode=source.spaceCode,
            policySignature=source.policySignature,
            revision=source.revision,
            chunkCount=source.chunkCount,
            tokenCount=source.tokenCount,
            errorCode=source.errorCode,
            lastIndexedAt=source.lastIndexedAt,
            metadata=dict(source.metadata),
        )
        if not updated:
            raise AIKnowledgeSourceInvalid("Knowledge source row was not found for update.")
        return sourceToEntity(
            AIKnowledgeSourceModel.objects.get(tenantId=source.tenantId, id=source.id)
        )

    def getSource(self, tenantId: uuid.UUID, sourceId: uuid.UUID) -> AIKnowledgeSourceRecord | None:
        row = AIKnowledgeSourceModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id=requireUuid(sourceId, "sourceId")
        ).first()
        return None if row is None else sourceToEntity(row)

    def findByNaturalKey(
        self,
        tenantId: uuid.UUID,
        sourceDomain: str,
        sourceEntityType: str,
        sourceEntityId: str,
    ) -> AIKnowledgeSourceRecord | None:
        row = AIKnowledgeSourceModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            sourceDomain=str(sourceDomain or "").strip().upper(),
            sourceEntityType=str(sourceEntityType or "").strip().upper(),
            sourceEntityId=str(sourceEntityId or "").strip(),
        ).first()
        return None if row is None else sourceToEntity(row)

    def listSources(
        self,
        tenantId: uuid.UUID,
        *,
        statuses: tuple[str, ...] = (),
        sourceDomain: str = "",
    ) -> tuple[AIKnowledgeSourceRecord, ...]:
        query = AIKnowledgeSourceModel.objects.filter(tenantId=requireUuid(tenantId, "tenantId"))
        if statuses:
            query = query.filter(status__in=[str(item).strip().upper() for item in statuses])
        if sourceDomain:
            query = query.filter(sourceDomain=str(sourceDomain).strip().upper())
        rows = query.order_by("sourceDomain", "sourceEntityType", "sourceEntityId")
        return tuple(sourceToEntity(row) for row in rows)

    def deleteSource(self, tenantId: uuid.UUID, sourceId: uuid.UUID) -> int:
        removed, _ = AIKnowledgeSourceModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id=requireUuid(sourceId, "sourceId")
        ).delete()
        return int(removed)

    def deleteSourcesBefore(
        self, tenantId: uuid.UUID | None, cutoff: datetime
    ) -> tuple[uuid.UUID, ...]:
        """Delete archived sources older than ``cutoff``; return their ids.

        Only ``ARCHIVED`` rows are eligible: retention must never silently
        drop a live index (contract §R.11).
        """

        query = AIKnowledgeSourceModel.objects.filter(status="ARCHIVED", updatedAt__lt=cutoff)
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        identifiers = tuple(query.values_list("id", flat=True))
        if identifiers:
            AIKnowledgeSourceModel.objects.filter(id__in=list(identifiers)).delete()
        return identifiers


class DjangoKnowledgeChunkStore:
    """``KnowledgeChunkStore`` over ``aiKnowledgeChunkRecords``."""

    def saveChunks(
        self, chunks: tuple[AIKnowledgeChunkRecord, ...]
    ) -> tuple[AIKnowledgeChunkRecord, ...]:
        if not chunks:
            return ()
        rows = [
            AIKnowledgeChunkRecordModel(
                id=chunk.id,
                tenantId=chunk.tenantId,
                source_id=chunk.sourceId,
                ordinal=chunk.ordinal,
                text=chunk.text,
                checksum=chunk.checksum,
                tokenCount=chunk.tokenCount,
                startOffset=chunk.startOffset,
                endOffset=chunk.endOffset,
                classification=chunk.classification,
                metadata=dict(chunk.metadata),
            )
            for chunk in chunks
        ]
        with transaction.atomic():
            AIKnowledgeChunkRecordModel.objects.bulk_create(rows)
        stored = AIKnowledgeChunkRecordModel.objects.filter(
            id__in=[chunk.id for chunk in chunks]
        ).order_by("ordinal")
        return tuple(chunkToEntity(row) for row in stored)

    def listChunks(
        self, tenantId: uuid.UUID, sourceId: uuid.UUID
    ) -> tuple[AIKnowledgeChunkRecord, ...]:
        rows = AIKnowledgeChunkRecordModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), source_id=requireUuid(sourceId, "sourceId")
        ).order_by("ordinal", "id")
        return tuple(chunkToEntity(row) for row in rows)

    def getChunk(self, tenantId: uuid.UUID, chunkId: uuid.UUID) -> AIKnowledgeChunkRecord | None:
        row = AIKnowledgeChunkRecordModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id=requireUuid(chunkId, "chunkId")
        ).first()
        return None if row is None else chunkToEntity(row)

    def reorderChunks(self, tenantId: uuid.UUID, ordinals: dict[uuid.UUID, int]) -> int:
        if not ordinals:
            return 0
        tenant = requireUuid(tenantId, "tenantId")
        moved = 0
        with transaction.atomic():
            AIKnowledgeChunkRecordModel.objects.filter(
                tenantId=tenant, id__in=list(ordinals)
            ).update(ordinal=_ORDINAL_SHIFT)
            for chunkId, ordinal in ordinals.items():
                moved += AIKnowledgeChunkRecordModel.objects.filter(
                    tenantId=tenant, id=chunkId
                ).update(ordinal=int(ordinal))
        return moved

    def reclassifyChunks(
        self, tenantId: uuid.UUID, sourceId: uuid.UUID, classification: str
    ) -> int:
        """Propagate a source classification change to its stored chunks.

        Reused chunks survive a reindex by checksum, so without this their
        inherited classification would stay at the previous (possibly more
        permissive) level and the Phase 13-K filter would keep letting them
        through — see the Phase 13-S execution report §5.
        """

        return int(
            AIKnowledgeChunkRecordModel.objects.filter(
                tenantId=requireUuid(tenantId, "tenantId"),
                source_id=requireUuid(sourceId, "sourceId"),
            )
            .exclude(classification=classification)
            .update(classification=classification)
        )

    def deleteChunks(self, tenantId: uuid.UUID, chunkIds: tuple[uuid.UUID, ...]) -> int:
        if not chunkIds:
            return 0
        removed, _ = AIKnowledgeChunkRecordModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id__in=list(chunkIds)
        ).delete()
        return int(removed)

    def deleteSourceChunks(self, tenantId: uuid.UUID, sourceId: uuid.UUID) -> int:
        removed, _ = AIKnowledgeChunkRecordModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), source_id=requireUuid(sourceId, "sourceId")
        ).delete()
        return int(removed)

    def countChunks(self, tenantId: uuid.UUID, sourceId: uuid.UUID) -> int:
        return int(
            AIKnowledgeChunkRecordModel.objects.filter(
                tenantId=requireUuid(tenantId, "tenantId"),
                source_id=requireUuid(sourceId, "sourceId"),
            ).count()
        )


__all__ = [
    "DjangoKnowledgeChunkStore",
    "DjangoKnowledgeSourceStore",
    "chunkToEntity",
    "sourceToEntity",
]
