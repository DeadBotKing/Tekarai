"""Phase 13-R integration tests — the knowledge stores over real SQLite.

Covers the ``aiKnowledgeSources`` and ``aiKnowledgeChunkRecords``
persistence contract: register round trips, lookup by the owning-domain
natural key, listing with status and domain filters, lifecycle updates,
the database-level uniqueness of one source per business row, bulk chunk
writes, the two-phase reorder that powers incremental reindexing (including
a full position swap), targeted and bulk deletes, the archived-only
retention sweep, and the cascade from source to chunks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.ai.domain.entities.knowledgeRecords import (
    AIKnowledgeChunkRecord,
    AIKnowledgeSourceRecord,
)
from apps.ai.domain.exceptions import AIKnowledgeSourceInvalid
from apps.ai.domain.valueObjects.knowledgeTypes import (
    ChunkingPolicy,
    chunkChecksum,
    contentChecksum,
)
from apps.ai.infrastructure.models import (
    AIKnowledgeChunkRecordModel,
    AIKnowledgeSourceModel,
)
from apps.ai.infrastructure.repositories.knowledgeRepositories import (
    DjangoKnowledgeChunkStore,
    DjangoKnowledgeSourceStore,
    chunkToEntity,
    sourceToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class DjangoKnowledgeSourceStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = DjangoKnowledgeSourceStore()

    def record(self, entityId: str = "doc-1", **overrides: object) -> AIKnowledgeSourceRecord:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "sourceDomain": overrides.pop("sourceDomain", "DOCUMENTS"),
            "sourceEntityType": overrides.pop("sourceEntityType", "DOCUMENT"),
            "sourceEntityId": entityId,
            "title": "Quarterly report",
            "checksum": contentChecksum(f"body-{entityId}"),
            "classification": overrides.pop("classification", "INTERNAL"),
            "spaceCode": "KNOWLEDGE_SPACE",
            "createdAt": CLOCK,
            "updatedAt": CLOCK,
        }
        params.update(overrides)
        return AIKnowledgeSourceRecord(**params)

    def testRoundTripPreservesEveryField(self) -> None:
        stored = self.store.saveSource(self.record())
        loaded = self.store.getSource(self.tenantId, stored.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.reference(), "DOCUMENTS:DOCUMENT:doc-1")
        self.assertEqual(loaded.checksum, stored.checksum)
        self.assertEqual(loaded.spaceCode, "KNOWLEDGE_SPACE")
        self.assertEqual(loaded.status, "PENDING")
        self.assertEqual(loaded.revision, 0)

    def testLookupByNaturalKeyIsNormalizedAndTenantScoped(self) -> None:
        self.store.saveSource(self.record())
        self.assertIsNotNone(
            self.store.findByNaturalKey(self.tenantId, "documents", "document", "doc-1")
        )
        self.assertIsNone(
            self.store.findByNaturalKey(self.otherTenantId, "DOCUMENTS", "DOCUMENT", "doc-1")
        )
        self.assertIsNone(
            self.store.findByNaturalKey(self.tenantId, "DOCUMENTS", "DOCUMENT", "doc-2")
        )

    def testGetIsTenantScoped(self) -> None:
        stored = self.store.saveSource(self.record())
        self.assertIsNone(self.store.getSource(self.otherTenantId, stored.id))

    def testOneSourcePerBusinessRowIsEnforcedByTheDatabase(self) -> None:
        self.store.saveSource(self.record())
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveSource(self.record())

    def testTheSameBusinessRowMayExistInTwoTenants(self) -> None:
        self.store.saveSource(self.record())
        self.store.saveSource(self.record(tenantId=self.otherTenantId))
        self.assertEqual(AIKnowledgeSourceModel.objects.filter(sourceEntityId="doc-1").count(), 2)

    def testUpdatePersistsTheWholeLifecycleState(self) -> None:
        stored = self.store.saveSource(self.record())
        stored.transitionTo("INDEXING", now=CLOCK)
        stored.markIndexed(
            checksum=contentChecksum("new body"),
            chunkCount=4,
            tokenCount=120,
            policy=ChunkingPolicy(),
            now=CLOCK,
        )
        updated = self.store.updateSource(stored)
        self.assertEqual(updated.status, "READY")
        self.assertEqual(updated.revision, 1)
        self.assertEqual(updated.chunkCount, 4)
        self.assertEqual(updated.tokenCount, 120)
        self.assertEqual(updated.policySignature, ChunkingPolicy().signature())
        self.assertEqual(updated.lastIndexedAt, CLOCK)

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        with self.assertRaises(AIKnowledgeSourceInvalid):
            self.store.updateSource(self.record("ghost"))

    def testListingIsOrderedFilterableAndTenantScoped(self) -> None:
        self.store.saveSource(self.record("doc-2"))
        self.store.saveSource(self.record("doc-1"))
        self.store.saveSource(
            self.record("m-1", sourceDomain="MEETINGS", sourceEntityType="MEETING", status="READY")
        )
        self.store.saveSource(self.record("foreign", tenantId=self.otherTenantId))
        allRows = self.store.listSources(self.tenantId)
        self.assertEqual([row.sourceEntityId for row in allRows], ["doc-1", "doc-2", "m-1"])
        meetings = self.store.listSources(self.tenantId, sourceDomain="MEETINGS")
        self.assertEqual(len(meetings), 1)
        ready = self.store.listSources(self.tenantId, statuses=("READY",))
        self.assertEqual(len(ready), 1)
        self.assertEqual(len(self.store.listSources(self.otherTenantId)), 1)

    def testDeleteIsTenantScoped(self) -> None:
        stored = self.store.saveSource(self.record())
        self.assertEqual(self.store.deleteSource(self.otherTenantId, stored.id), 0)
        self.assertEqual(self.store.deleteSource(self.tenantId, stored.id), 1)

    def testRetentionSweepOnlyTouchesArchivedRows(self) -> None:
        live = self.store.saveSource(self.record("doc-live", status="READY"))
        archived = self.store.saveSource(self.record("doc-old", status="ARCHIVED"))
        AIKnowledgeSourceModel.objects.filter(id__in=[live.id, archived.id]).update(
            updatedAt=CLOCK - timedelta(days=900)
        )
        removed = self.store.deleteSourcesBefore(self.tenantId, CLOCK - timedelta(days=30))
        self.assertEqual(removed, (archived.id,))
        self.assertTrue(AIKnowledgeSourceModel.objects.filter(id=live.id).exists())

    def testRetentionSweepCanRunAcrossAllTenants(self) -> None:
        first = self.store.saveSource(self.record("a", status="ARCHIVED"))
        second = self.store.saveSource(
            self.record("b", tenantId=self.otherTenantId, status="ARCHIVED")
        )
        AIKnowledgeSourceModel.objects.filter(id__in=[first.id, second.id]).update(
            updatedAt=CLOCK - timedelta(days=900)
        )
        self.assertEqual(len(self.store.deleteSourcesBefore(None, CLOCK - timedelta(days=30))), 2)

    def testMapperProducesAValidatedEntity(self) -> None:
        self.store.saveSource(self.record())
        row = AIKnowledgeSourceModel.objects.get(tenantId=self.tenantId)
        entity = sourceToEntity(row)
        self.assertIsInstance(entity, AIKnowledgeSourceRecord)
        self.assertEqual(entity.naturalKey, ("DOCUMENTS", "DOCUMENT", "doc-1"))


class DjangoKnowledgeChunkStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.sourceStore = DjangoKnowledgeSourceStore()
        self.store = DjangoKnowledgeChunkStore()
        self.source = self.sourceStore.saveSource(
            AIKnowledgeSourceRecord(
                tenantId=self.tenantId,
                sourceDomain="DOCUMENTS",
                sourceEntityType="DOCUMENT",
                sourceEntityId="doc-1",
                title="Report",
                checksum=contentChecksum("body"),
                createdAt=CLOCK,
                updatedAt=CLOCK,
            )
        )

    def chunk(self, ordinal: int, text: str, **overrides: object) -> AIKnowledgeChunkRecord:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "sourceId": overrides.pop("sourceId", self.source.id),
            "ordinal": ordinal,
            "text": text,
            "checksum": chunkChecksum(text),
            "tokenCount": max(1, len(text) // 4),
            "startOffset": ordinal * 100,
            "endOffset": ordinal * 100 + len(text),
            "metadata": {"reference": "DOCUMENTS:DOCUMENT:doc-1"},
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIKnowledgeChunkRecord(**params)

    def seed(self, count: int = 3) -> tuple[AIKnowledgeChunkRecord, ...]:
        return self.store.saveChunks(
            tuple(self.chunk(index, f"paragraph number {index}") for index in range(count))
        )

    def testBulkWriteRoundTrip(self) -> None:
        stored = self.seed()
        self.assertEqual(len(stored), 3)
        loaded = self.store.listChunks(self.tenantId, self.source.id)
        self.assertEqual([chunk.ordinal for chunk in loaded], [0, 1, 2])
        self.assertEqual(loaded[0].metadata["reference"], "DOCUMENTS:DOCUMENT:doc-1")
        self.assertEqual(loaded[0].text, "paragraph number 0")

    def testEmptyWriteIsANoop(self) -> None:
        self.assertEqual(self.store.saveChunks(()), ())
        self.assertEqual(self.store.countChunks(self.tenantId, self.source.id), 0)

    def testReadsAreTenantScoped(self) -> None:
        stored = self.seed()
        self.assertIsNone(self.store.getChunk(self.otherTenantId, stored[0].id))
        self.assertEqual(self.store.listChunks(self.otherTenantId, self.source.id), ())
        self.assertEqual(self.store.countChunks(self.otherTenantId, self.source.id), 0)

    def testGetChunkReturnsTheWholeRecord(self) -> None:
        stored = self.seed()
        loaded = self.store.getChunk(self.tenantId, stored[1].id)
        assert loaded is not None
        self.assertEqual(loaded.ordinal, 1)
        self.assertEqual(loaded.checksum, stored[1].checksum)
        self.assertEqual(loaded.embeddingSourceId, str(stored[1].id))

    def testReorderShiftsChunksToNewPositions(self) -> None:
        stored = self.seed()
        moved = self.store.reorderChunks(
            self.tenantId, {stored[0].id: 1, stored[1].id: 2, stored[2].id: 3}
        )
        self.assertEqual(moved, 3)
        loaded = self.store.listChunks(self.tenantId, self.source.id)
        self.assertEqual([chunk.ordinal for chunk in loaded], [1, 2, 3])

    def testReorderCanSwapTwoPositions(self) -> None:
        stored = self.seed(2)
        self.store.reorderChunks(self.tenantId, {stored[0].id: 1, stored[1].id: 0})
        loaded = self.store.listChunks(self.tenantId, self.source.id)
        self.assertEqual(
            [chunk.text for chunk in loaded], ["paragraph number 1", "paragraph number 0"]
        )

    def testReorderIsTenantScopedAndEmptySafe(self) -> None:
        stored = self.seed(1)
        self.assertEqual(self.store.reorderChunks(self.tenantId, {}), 0)
        self.assertEqual(self.store.reorderChunks(self.otherTenantId, {stored[0].id: 5}), 0)

    def testTargetedDeleteRemovesOnlyTheGivenChunks(self) -> None:
        stored = self.seed()
        removed = self.store.deleteChunks(self.tenantId, (stored[0].id, stored[2].id))
        self.assertEqual(removed, 2)
        remaining = self.store.listChunks(self.tenantId, self.source.id)
        self.assertEqual([chunk.text for chunk in remaining], ["paragraph number 1"])

    def testTargetedDeleteIsTenantScopedAndEmptySafe(self) -> None:
        stored = self.seed(1)
        self.assertEqual(self.store.deleteChunks(self.tenantId, ()), 0)
        self.assertEqual(self.store.deleteChunks(self.otherTenantId, (stored[0].id,)), 0)
        self.assertEqual(self.store.countChunks(self.tenantId, self.source.id), 1)

    def testSourceDeleteRemovesEveryChunk(self) -> None:
        self.seed()
        self.assertEqual(self.store.deleteSourceChunks(self.tenantId, self.source.id), 3)
        self.assertEqual(self.store.countChunks(self.tenantId, self.source.id), 0)

    def testDeletingTheSourceCascadesToItsChunks(self) -> None:
        self.seed()
        self.sourceStore.deleteSource(self.tenantId, self.source.id)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 0)

    def testChunksOfTwoSourcesStaySeparate(self) -> None:
        other = self.sourceStore.saveSource(
            AIKnowledgeSourceRecord(
                tenantId=self.tenantId,
                sourceDomain="MEETINGS",
                sourceEntityType="MEETING",
                sourceEntityId="m-1",
                title="Standup",
                checksum=contentChecksum("notes"),
                createdAt=CLOCK,
                updatedAt=CLOCK,
            )
        )
        self.seed(2)
        self.store.saveChunks((self.chunk(0, "meeting note", sourceId=other.id),))
        self.assertEqual(self.store.countChunks(self.tenantId, self.source.id), 2)
        self.assertEqual(self.store.countChunks(self.tenantId, other.id), 1)

    def testMapperProducesAValidatedEntity(self) -> None:
        stored = self.seed(1)
        row = AIKnowledgeChunkRecordModel.objects.get(id=stored[0].id)
        entity = chunkToEntity(row)
        self.assertIsInstance(entity, AIKnowledgeChunkRecord)
        self.assertEqual(entity.sourceId, self.source.id)
        self.assertEqual(entity.checksum, chunkChecksum("paragraph number 0"))

    def testUnknownChunkReadsAsNone(self) -> None:
        self.assertIsNone(self.store.getChunk(self.tenantId, uuid.uuid4()))

    def testReclassifyPropagatesToEveryChunkOfTheSource(self) -> None:
        stored = self.seed(3)
        changed = self.store.reclassifyChunks(self.tenantId, self.source.id, "RESTRICTED")
        self.assertEqual(changed, 3)
        for chunk in self.store.listChunks(self.tenantId, self.source.id):
            self.assertEqual(chunk.classification, "RESTRICTED")
        self.assertEqual(stored[0].classification, "INTERNAL")

    def testReclassifyIsIdempotentAndTenantScoped(self) -> None:
        self.seed(2)
        self.store.reclassifyChunks(self.tenantId, self.source.id, "CONFIDENTIAL")
        self.assertEqual(
            self.store.reclassifyChunks(self.tenantId, self.source.id, "CONFIDENTIAL"), 0
        )
        self.assertEqual(
            self.store.reclassifyChunks(self.otherTenantId, self.source.id, "PUBLIC"), 0
        )
