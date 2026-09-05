"""Phase 13-Q integration tests — the embedding stores over real SQLite.

Covers the ``aiVectorSpaces`` and ``aiEmbeddingVectors`` persistence
contract: round trips that preserve the vector geometry, the tenant- and
space-scoped reads, the idempotent cache-key save, the candidate scan with
its filters and ceiling, deletes (by source, by space, by cutoff), the
database-level uniqueness guarantees, and the guard that refuses to
rehydrate a vector whose space registration is gone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.ai.domain.entities.embeddingRecords import (
    AIStoredEmbedding,
    AIVectorSpaceDefinition,
)
from apps.ai.domain.exceptions import AIVectorSpaceInvalid
from apps.ai.domain.valueObjects.embeddingTypes import (
    VectorSpace,
    contentFingerprint,
    isUnitVector,
    normalizeVector,
)
from apps.ai.infrastructure.models import AIStoredEmbeddingModel, AIVectorSpaceModel
from apps.ai.infrastructure.repositories.embeddingRepositories import (
    DjangoEmbeddingStore,
    DjangoVectorSpaceStore,
    embeddingToEntity,
    spaceToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def makeSpace(code: str = "KPI_SPACE", **overrides: object) -> VectorSpace:
    params: dict = {
        "code": code,
        "modelCode": "TEXT_EMBED_3",
        "dimensions": 4,
        "metric": "COSINE",
        "normalization": "L2",
    }
    params.update(overrides)
    return VectorSpace(**params)


class DjangoVectorSpaceStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = DjangoVectorSpaceStore()

    def define(self, code: str = "KPI_SPACE", **overrides: object) -> AIVectorSpaceDefinition:
        definition = AIVectorSpaceDefinition(
            tenantId=overrides.pop("tenantId", self.tenantId),  # type: ignore[arg-type]
            space=makeSpace(code, **overrides),
            providerCode="LOCAL",
            description="kpi vectors",
        )
        return self.store.saveSpace(definition)

    def testRoundTripPreservesTheSpaceGeometry(self) -> None:
        stored = self.define()
        loaded = self.store.getSpace(self.tenantId, "KPI_SPACE")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.id, stored.id)
        self.assertEqual(loaded.space.signature(), stored.space.signature())
        self.assertEqual(loaded.providerCode, "LOCAL")
        self.assertEqual(loaded.description, "kpi vectors")
        self.assertTrue(loaded.isActive)

    def testNonDefaultGeometryIsPersistedVerbatim(self) -> None:
        self.define(
            "EUCLID_SPACE",
            dimensions=8,
            metric="EUCLIDEAN",
            normalization="NONE",
            modelVersion="2026-01",
        )
        loaded = self.store.getSpace(self.tenantId, "EUCLID_SPACE")
        assert loaded is not None
        self.assertEqual(loaded.space.dimensions, 8)
        self.assertEqual(loaded.space.metric, "EUCLIDEAN")
        self.assertEqual(loaded.space.normalization, "NONE")
        self.assertEqual(loaded.space.modelVersion, "2026-01")

    def testLookupNormalizesTheCodeAndIsTenantScoped(self) -> None:
        self.define()
        self.assertIsNotNone(self.store.getSpace(self.tenantId, " kpi_space "))
        self.assertIsNone(self.store.getSpace(self.otherTenantId, "KPI_SPACE"))
        self.assertIsNone(self.store.getSpace(self.tenantId, "MISSING"))

    def testListingIsOrderedAndTenantScoped(self) -> None:
        self.define("ZULU_SPACE")
        self.define("ALPHA_SPACE")
        self.define("FOREIGN_SPACE", tenantId=self.otherTenantId)
        codes = [item.space.code for item in self.store.listSpaces(self.tenantId)]
        self.assertEqual(codes, ["ALPHA_SPACE", "ZULU_SPACE"])
        self.assertEqual(len(self.store.listSpaces(self.otherTenantId)), 1)

    def testUpdatePersistsLifecycleFields(self) -> None:
        stored = self.define()
        stored.deactivate(now=CLOCK)
        stored.description = "drained"
        updated = self.store.updateSpace(stored)
        self.assertFalse(updated.isActive)
        self.assertEqual(updated.description, "drained")
        reloaded = self.store.getSpace(self.tenantId, "KPI_SPACE")
        assert reloaded is not None
        self.assertFalse(reloaded.isActive)

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        orphan = AIVectorSpaceDefinition(tenantId=self.tenantId, space=makeSpace("GHOST_SPACE"))
        with self.assertRaises(AIVectorSpaceInvalid):
            self.store.updateSpace(orphan)

    def testSpaceCodeIsUniquePerTenantAtTheDatabaseLevel(self) -> None:
        self.define()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.define()

    def testTheSameCodeMayExistInTwoTenants(self) -> None:
        self.define()
        self.define(tenantId=self.otherTenantId)
        self.assertEqual(AIVectorSpaceModel.objects.filter(code="KPI_SPACE").count(), 2)

    def testMapperProducesAValidatedEntity(self) -> None:
        self.define()
        row = AIVectorSpaceModel.objects.get(tenantId=self.tenantId, code="KPI_SPACE")
        entity = spaceToEntity(row)
        self.assertIsInstance(entity, AIVectorSpaceDefinition)
        self.assertEqual(entity.space.dimensions, 4)


class DjangoEmbeddingStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.spaceStore = DjangoVectorSpaceStore()
        self.store = DjangoEmbeddingStore(self.spaceStore)
        self.space = makeSpace()
        for tenant in (self.tenantId, self.otherTenantId):
            self.spaceStore.saveSpace(
                AIVectorSpaceDefinition(tenantId=tenant, space=self.space, providerCode="LOCAL")
            )

    def embedding(
        self,
        text: str = "kpi trend",
        *,
        tenantId: uuid.UUID | None = None,
        sourceType: str = "KNOWLEDGE_CHUNK",
        sourceId: str = "chunk-1",
        vector: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0),
        createdAt: datetime | None = None,
        space: VectorSpace | None = None,
    ) -> AIStoredEmbedding:
        chosen = space or self.space
        return AIStoredEmbedding(
            tenantId=tenantId or self.tenantId,
            space=chosen,
            sourceType=sourceType,
            sourceId=sourceId,
            vector=normalizeVector(vector),
            contentHash=contentFingerprint(text, chosen),
            providerCode="LOCAL",
            tokenCount=3,
            metadata={"origin": "test"},
            createdAt=createdAt or CLOCK,
        )

    def testRoundTripPreservesVectorAndMetadata(self) -> None:
        stored = self.store.saveEmbedding(self.embedding())
        loaded = self.store.getEmbedding(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.id, stored.id)
        self.assertEqual(loaded.vector, stored.vector)
        self.assertTrue(isUnitVector(loaded.vector))
        self.assertEqual(loaded.metadata, {"origin": "test"})
        self.assertEqual(loaded.tokenCount, 3)
        self.assertEqual(loaded.space.signature(), self.space.signature())

    def testFloatFidelitySurvivesTheJsonColumn(self) -> None:
        vector = normalizeVector((0.123456789, 0.987654321, 0.5, 0.25))
        stored = self.store.saveEmbedding(self.embedding(vector=vector))
        loaded = self.store.getEmbedding(self.tenantId, stored.id)
        assert loaded is not None
        for original, restored in zip(stored.vector, loaded.vector, strict=True):
            self.assertAlmostEqual(original, restored, places=12)

    def testSavingTheSameContentTwiceIsIdempotent(self) -> None:
        first = self.store.saveEmbedding(self.embedding())
        second = self.store.saveEmbedding(self.embedding())
        self.assertEqual(first.id, second.id)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 1)

    def testSaveManyReturnsEveryRow(self) -> None:
        rows = self.store.saveMany(
            (
                self.embedding("kpi trend", sourceId="chunk-1"),
                self.embedding("budget plan", sourceId="chunk-2", vector=(0.0, 1.0, 0.0, 0.0)),
            )
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.store.countForSpace(self.tenantId, "KPI_SPACE"), 2)

    def testReadsAreTenantScoped(self) -> None:
        stored = self.store.saveEmbedding(self.embedding())
        self.assertIsNone(self.store.getEmbedding(self.otherTenantId, stored.id))
        self.assertEqual(self.store.countForSpace(self.otherTenantId, "KPI_SPACE"), 0)

    def testFingerprintLookupReturnsOnlyRequestedRows(self) -> None:
        first = self.store.saveEmbedding(self.embedding("kpi trend"))
        self.store.saveEmbedding(
            self.embedding("budget plan", sourceId="chunk-2", vector=(0.0, 1.0, 0.0, 0.0))
        )
        found = self.store.findByFingerprints(self.tenantId, "KPI_SPACE", (first.contentHash,))
        self.assertEqual([row.id for row in found], [first.id])
        self.assertEqual(self.store.findByFingerprints(self.tenantId, "KPI_SPACE", ()), ())

    def testFingerprintLookupDoesNotLeakAcrossTenants(self) -> None:
        mine = self.store.saveEmbedding(self.embedding())
        self.store.saveEmbedding(self.embedding(tenantId=self.otherTenantId))
        found = self.store.findByFingerprints(self.otherTenantId, "KPI_SPACE", (mine.contentHash,))
        self.assertEqual(len(found), 1)
        self.assertNotEqual(found[0].id, mine.id)

    def testListBySourceIsScopedAndOrdered(self) -> None:
        self.store.saveEmbedding(self.embedding("kpi trend", sourceId="doc-1"))
        self.store.saveEmbedding(
            self.embedding(
                "budget plan",
                sourceId="doc-1",
                vector=(0.0, 1.0, 0.0, 0.0),
                createdAt=CLOCK + timedelta(minutes=1),
            )
        )
        self.store.saveEmbedding(
            self.embedding("other note", sourceId="doc-2", vector=(0.0, 0.0, 1.0, 0.0))
        )
        rows = self.store.listBySource(self.tenantId, "KPI_SPACE", "KNOWLEDGE_CHUNK", "doc-1")
        self.assertEqual(len(rows), 2)
        self.assertLessEqual(rows[0].createdAt, rows[1].createdAt)

    def testScanHonoursSourceTypeFilterAndLimit(self) -> None:
        self.store.saveEmbedding(self.embedding("kpi trend", sourceType="DOCUMENT", sourceId="a"))
        self.store.saveEmbedding(
            self.embedding(
                "budget plan", sourceType="MESSAGE", sourceId="b", vector=(0.0, 1.0, 0.0, 0.0)
            )
        )
        self.store.saveEmbedding(
            self.embedding(
                "other note", sourceType="MESSAGE", sourceId="c", vector=(0.0, 0.0, 1.0, 0.0)
            )
        )
        messages = self.store.scanCandidates(self.tenantId, "KPI_SPACE", sourceTypes=("MESSAGE",))
        self.assertEqual({row.sourceType for row in messages}, {"MESSAGE"})
        limited = self.store.scanCandidates(self.tenantId, "KPI_SPACE", limit=1)
        self.assertEqual(len(limited), 1)

    def testScanIsSpaceScoped(self) -> None:
        other = makeSpace("OTHER_SPACE", dimensions=4)
        self.spaceStore.saveSpace(
            AIVectorSpaceDefinition(tenantId=self.tenantId, space=other, providerCode="LOCAL")
        )
        self.store.saveEmbedding(self.embedding())
        self.store.saveEmbedding(self.embedding("kpi trend", space=other, sourceId="chunk-9"))
        self.assertEqual(len(self.store.scanCandidates(self.tenantId, "KPI_SPACE")), 1)
        self.assertEqual(len(self.store.scanCandidates(self.tenantId, "OTHER_SPACE")), 1)

    def testDeleteBySourceRemovesOnlyThatSource(self) -> None:
        self.store.saveEmbedding(self.embedding("kpi trend", sourceId="doc-1"))
        self.store.saveEmbedding(
            self.embedding("budget plan", sourceId="doc-2", vector=(0.0, 1.0, 0.0, 0.0))
        )
        removed = self.store.deleteBySource(self.tenantId, "KPI_SPACE", "KNOWLEDGE_CHUNK", "doc-1")
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.countForSpace(self.tenantId, "KPI_SPACE"), 1)

    def testDeleteSpaceEmbeddingsIsTenantScoped(self) -> None:
        self.store.saveEmbedding(self.embedding())
        self.store.saveEmbedding(self.embedding(tenantId=self.otherTenantId))
        self.assertEqual(self.store.deleteSpaceEmbeddings(self.tenantId, "KPI_SPACE"), 1)
        self.assertEqual(self.store.countForSpace(self.otherTenantId, "KPI_SPACE"), 1)

    def testRetentionDeleteHonoursTheCutoffAndTenantScope(self) -> None:
        old = self.store.saveEmbedding(self.embedding("kpi trend"))
        AIStoredEmbeddingModel.objects.filter(id=old.id).update(
            createdAt=CLOCK - timedelta(days=400)
        )
        self.store.saveEmbedding(
            self.embedding("budget plan", sourceId="chunk-2", vector=(0.0, 1.0, 0.0, 0.0))
        )
        removed = self.store.deleteEmbeddingsBefore(self.tenantId, CLOCK - timedelta(days=30))
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.countForSpace(self.tenantId, "KPI_SPACE"), 1)

    def testRetentionDeleteCanRunAcrossAllTenants(self) -> None:
        first = self.store.saveEmbedding(self.embedding())
        second = self.store.saveEmbedding(self.embedding(tenantId=self.otherTenantId))
        AIStoredEmbeddingModel.objects.filter(id__in=[first.id, second.id]).update(
            createdAt=CLOCK - timedelta(days=400)
        )
        self.assertEqual(self.store.deleteEmbeddingsBefore(None, CLOCK - timedelta(days=30)), 2)

    def testCacheKeyIsUniquePerTenantAndSpace(self) -> None:
        self.store.saveEmbedding(self.embedding())
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIStoredEmbeddingModel.objects.create(
                tenantId=self.tenantId,
                spaceCode="KPI_SPACE",
                sourceType="DOCUMENT",
                sourceId="dupe",
                dimensions=4,
                vector=[1.0, 0.0, 0.0, 0.0],
                contentHash=contentFingerprint("kpi trend", self.space),
            )

    def testOrphanRowRefusesToRehydrate(self) -> None:
        stored = self.store.saveEmbedding(self.embedding())
        AIVectorSpaceModel.objects.filter(tenantId=self.tenantId, code="KPI_SPACE").delete()
        freshStore = DjangoEmbeddingStore(DjangoVectorSpaceStore())
        with self.assertRaises(AIVectorSpaceInvalid):
            freshStore.getEmbedding(self.tenantId, stored.id)

    def testMapperProducesAValidatedEntity(self) -> None:
        stored = self.store.saveEmbedding(self.embedding())
        row = AIStoredEmbeddingModel.objects.get(id=stored.id)
        entity = embeddingToEntity(row, self.space)
        self.assertIsInstance(entity, AIStoredEmbedding)
        self.assertTrue(entity.matchesContent("kpi trend"))

    def testUnknownEmbeddingReadsAsNone(self) -> None:
        self.assertIsNone(self.store.getEmbedding(self.tenantId, uuid.uuid4()))
