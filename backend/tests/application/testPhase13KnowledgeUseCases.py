"""Phase 13-R application tests — knowledge ingestion over a real SQLite DB.

Covers first ingestion, idempotent re-ingestion, incremental reindexing
(append, insert-at-top, deletion, policy change, forced run), the vertical
wiring into the real Phase 13-Q embedding service (chunk vectors created,
reused, and deleted), failure bookkeeping, archive and delete lifecycles,
retention, tenant isolation, the fail-closed switch, audit entries in the
real Phase 13-O ledger, chunk resolution for the future S pipeline, and the
Phase 13-P ``INDEXING`` job handler end-to-end.

Only the embedding *provider* is a double; the knowledge stores, the
embedding service, the embedding stores, and the audit ledger are all real.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from django.test import TestCase

from apps.ai.application.services.auditService import AuditApplicationService, AuditSettings
from apps.ai.application.services.embeddingService import (
    DefineVectorSpaceCommand,
    EmbeddingApplicationService,
    EmbeddingSettings,
    SimilaritySearchQuery,
)
from apps.ai.application.services.knowledgeService import (
    AUDIT_KNOWLEDGE_ARCHIVED,
    AUDIT_KNOWLEDGE_INGESTED,
    AUDIT_KNOWLEDGE_PURGED,
    AUDIT_KNOWLEDGE_REINDEXED,
    IngestKnowledgeCommand,
    KnowledgeApplicationService,
    KnowledgeIngestionJobHandler,
    KnowledgeSettings,
)
from apps.ai.application.services.queueService import (
    QueueApplicationService,
    QueueSettings,
    SubmitJobCommand,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIKnowledgeChunkInvalid,
    AIKnowledgeChunkNotFound,
    AIKnowledgeIngestionFailed,
    AIKnowledgeSourceArchived,
    AIKnowledgeSourceInvalid,
    AIKnowledgeSourceNotFound,
)
from apps.ai.domain.valueObjects.embeddingTypes import VectorSpace
from apps.ai.domain.valueObjects.knowledgeTypes import ChunkingPolicy
from apps.ai.infrastructure.models import (
    AIKnowledgeChunkRecordModel,
    AIKnowledgeSourceModel,
    AIStoredEmbeddingModel,
)
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)
from apps.ai.infrastructure.repositories.embeddingRepositories import (
    DjangoEmbeddingStore,
    DjangoVectorSpaceStore,
)
from apps.ai.infrastructure.repositories.knowledgeRepositories import (
    DjangoKnowledgeChunkStore,
    DjangoKnowledgeSourceStore,
)
from apps.ai.infrastructure.repositories.queueRepositories import DjangoJobStore

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)

PARAGRAPH_ONE = "The quarterly production report covers three pharmaceutical lines."
PARAGRAPH_TWO = "Line one reached ninety two percent of its planned output."
PARAGRAPH_THREE = "Line two was halted twice for preventive maintenance."
PARAGRAPH_FOUR = "Line three exceeded its target by four percent overall."
DOCUMENT = "\n\n".join((PARAGRAPH_ONE, PARAGRAPH_TWO, PARAGRAPH_THREE))


class HashProvider:
    """Deterministic offline embedding provider (content-sensitive)."""

    def __init__(self, dimensions: int = 4) -> None:
        self.dimensions = dimensions
        self.embedCalls: list[str] = []
        self.batchCalls: list[list[str]] = []

    def vectorFor(self, text: str) -> list[float]:
        digest = [0.0] * self.dimensions
        for index, character in enumerate(text):
            digest[index % self.dimensions] += (ord(character) % 17) + 1
        total = sum(digest) or 1.0
        return [value / total for value in digest]

    def embed(self, *, text: str, model: str, **kwargs: Any) -> list[float]:
        self.embedCalls.append(text)
        return self.vectorFor(text)

    def embedBatch(self, *, texts: Any, model: str, **kwargs: Any) -> list[list[float]]:
        materialized = list(texts)
        self.batchCalls.append(materialized)
        return [self.vectorFor(text) for text in materialized]

    @property
    def totalTexts(self) -> int:
        return len(self.embedCalls) + sum(len(call) for call in self.batchCalls)


class FixedResolver:
    def __init__(self, provider: HashProvider) -> None:
        self.provider = provider

    def providerFor(self, tenantId: uuid.UUID, space: VectorSpace) -> HashProvider:
        return self.provider


class ExplodingEmbedder:
    """Embedder double that fails, to prove failure bookkeeping."""

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def embedTexts(self, tenantId: Any, command: Any) -> Any:
        raise RuntimeError("provider exploded")

    def deleteSourceEmbeddings(
        self, tenantId: Any, spaceCode: str, sourceType: str, sourceId: str
    ) -> int:
        self.deleted.append(sourceId)
        return 0


class KnowledgeTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.provider = HashProvider()
        self.spaceStore = DjangoVectorSpaceStore()
        self.embeddingStore = DjangoEmbeddingStore(self.spaceStore)
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=AuditSettings(enabled=True, retentionDays=365),
            now=lambda: CLOCK,
        )
        self.embedding = EmbeddingApplicationService(
            self.spaceStore,
            self.embeddingStore,
            providerResolver=FixedResolver(self.provider),
            settings=EmbeddingSettings(maxBatchSize=8, searchCandidateLimit=100),
            auditLogger=self.audit,
            now=lambda: CLOCK,
        )
        self.embedding.defineVectorSpace(
            self.tenantId,
            DefineVectorSpaceCommand(
                code="KNOWLEDGE_SPACE",
                modelCode="TEXT_EMBED_3",
                dimensions=4,
                providerCode="LOCAL",
            ),
        )
        self.sourceStore = DjangoKnowledgeSourceStore()
        self.chunkStore = DjangoKnowledgeChunkStore()
        self.service = self.buildService()

    def buildService(self, **overrides: Any) -> KnowledgeApplicationService:
        settings = KnowledgeSettings(
            enabled=overrides.pop("enabled", True),
            strategy=overrides.pop("strategy", "PARAGRAPH"),
            chunkTokens=overrides.pop("chunkTokens", 20),
            overlapTokens=overrides.pop("overlapTokens", 0),
            minChunkTokens=overrides.pop("minChunkTokens", 0),
            autoEmbed=overrides.pop("autoEmbed", True),
            embedBatchSize=overrides.pop("embedBatchSize", 2),
            maxChunksPerSource=overrides.pop("maxChunksPerSource", 100),
            retentionDays=overrides.pop("retentionDays", 730),
        )
        return KnowledgeApplicationService(
            self.sourceStore,
            self.chunkStore,
            embedder=overrides.pop("embedder", self.embedding),
            settings=settings,
            auditLogger=overrides.pop("auditLogger", self.audit),
            now=lambda: CLOCK,
        )

    def command(self, content: str = DOCUMENT, **overrides: Any) -> IngestKnowledgeCommand:
        params: dict[str, Any] = {
            "sourceDomain": "DOCUMENTS",
            "sourceEntityType": "DOCUMENT",
            "sourceEntityId": "doc-1",
            "title": "Quarterly report",
            "content": content,
            "classification": "INTERNAL",
            "spaceCode": "KNOWLEDGE_SPACE",
        }
        params.update(overrides)
        return IngestKnowledgeCommand(**params)

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class FirstIngestionTests(KnowledgeTestCase):
    def testIngestionRegistersTheSourceAndItsChunks(self) -> None:
        result = self.service.ingestSource(self.tenantId, self.command())
        self.assertEqual(result.action, "CREATE")
        self.assertEqual(result.source.status, "READY")
        self.assertEqual(result.source.revision, 1)
        self.assertEqual(result.source.reference, "DOCUMENTS:DOCUMENT:doc-1")
        self.assertEqual(result.chunksAdded, 3)
        self.assertEqual(result.chunksReused, 0)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 3)
        self.assertEqual(result.source.chunkCount, 3)
        self.assertIn(AUDIT_KNOWLEDGE_INGESTED, self.auditActions())

    def testTheSourceContentItselfIsNeverStored(self) -> None:
        self.service.ingestSource(self.tenantId, self.command())
        row = AIKnowledgeSourceModel.objects.get(tenantId=self.tenantId)
        self.assertFalse(hasattr(row, "content"))
        self.assertEqual(len(row.checksum), 64)
        self.assertEqual(row.title, "Quarterly report")

    def testEveryNewChunkIsEmbeddedIntoTheVectorSpace(self) -> None:
        result = self.service.ingestSource(self.tenantId, self.command())
        self.assertEqual(result.embeddingsCreated, 3)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 3)
        stored = {row.sourceType for row in AIStoredEmbeddingModel.objects.all()}
        self.assertEqual(stored, {"KNOWLEDGE_CHUNK"})

    def testChunkVectorsAreAddressableByChunkId(self) -> None:
        self.service.ingestSource(self.tenantId, self.command())
        chunks = self.service.listChunks(
            self.tenantId,
            self.service.findSource(self.tenantId, "DOCUMENTS", "DOCUMENT", "doc-1").sourceId,
        )
        for chunk in chunks:
            rows = AIStoredEmbeddingModel.objects.filter(sourceId=str(chunk.chunkId))
            self.assertEqual(rows.count(), 1)

    def testEmbeddingBatchesFollowTheConfiguredSize(self) -> None:
        self.service.ingestSource(self.tenantId, self.command())
        self.assertEqual(self.provider.totalTexts, 3)

    def testChunksInheritTheSourceClassification(self) -> None:
        result = self.service.ingestSource(
            self.tenantId, self.command(classification="CONFIDENTIAL")
        )
        chunks = self.service.listChunks(self.tenantId, result.source.sourceId)
        self.assertEqual({chunk.classification for chunk in chunks}, {"CONFIDENTIAL"})

    def testChunkOrdinalsAreContiguous(self) -> None:
        result = self.service.ingestSource(self.tenantId, self.command())
        chunks = self.service.listChunks(self.tenantId, result.source.sourceId)
        self.assertEqual([chunk.ordinal for chunk in chunks], [0, 1, 2])

    def testIngestionWithoutASpaceSkipsEmbedding(self) -> None:
        result = self.service.ingestSource(self.tenantId, self.command(spaceCode=""))
        self.assertEqual(result.chunksAdded, 3)
        self.assertEqual(result.embeddingsCreated, 0)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 0)

    def testAutoEmbedCanBeDisabledPerCall(self) -> None:
        result = self.service.ingestSource(self.tenantId, self.command(autoEmbed=False))
        self.assertEqual(result.embeddingsCreated, 0)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 3)

    def testInvalidCommandsAreRejected(self) -> None:
        with self.assertRaises(AIKnowledgeSourceInvalid):
            self.service.ingestSource(self.tenantId, "ingest please")  # type: ignore[arg-type]
        with self.assertRaises(AIKnowledgeChunkInvalid):
            self.service.ingestSource(self.tenantId, self.command(content="   "))

    def testChunkCeilingIsEnforced(self) -> None:
        service = self.buildService(maxChunksPerSource=2)
        with self.assertRaises(AIKnowledgeSourceInvalid):
            service.ingestSource(self.tenantId, self.command())

    def testDisabledPlatformRefusesEverything(self) -> None:
        disabled = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            disabled.ingestSource(self.tenantId, self.command())
        with self.assertRaises(AIConfigurationError):
            disabled.listSources(self.tenantId)


class IncrementalReindexTests(KnowledgeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.first = self.service.ingestSource(self.tenantId, self.command())
        self.sourceId = self.first.source.sourceId

    def testUnchangedContentIsACompleteNoop(self) -> None:
        before = self.provider.totalTexts
        result = self.service.ingestSource(self.tenantId, self.command())
        self.assertTrue(result.isNoop)
        self.assertEqual(result.action, "UNCHANGED")
        self.assertEqual(result.chunksAdded, 0)
        self.assertEqual(self.provider.totalTexts, before)
        self.assertEqual(self.service.describeSource(self.tenantId, self.sourceId).revision, 1)

    def testAppendedParagraphOnlyEmbedsTheNewChunk(self) -> None:
        before = self.provider.totalTexts
        result = self.service.ingestSource(
            self.tenantId, self.command(f"{DOCUMENT}\n\n{PARAGRAPH_FOUR}")
        )
        self.assertEqual(result.action, "REINDEX")
        self.assertEqual(result.chunksAdded, 1)
        self.assertEqual(result.chunksReused, 3)
        self.assertEqual(result.chunksRemoved, 0)
        self.assertEqual(result.embeddingsCreated, 1)
        self.assertEqual(self.provider.totalTexts, before + 1)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 4)
        self.assertEqual(result.source.revision, 2)

    def testParagraphInsertedAtTheTopShiftsOrdinalsWithoutReembedding(self) -> None:
        before = self.provider.totalTexts
        result = self.service.ingestSource(
            self.tenantId, self.command(f"{PARAGRAPH_FOUR}\n\n{DOCUMENT}")
        )
        self.assertEqual(result.chunksReused, 3)
        self.assertEqual(result.chunksAdded, 1)
        self.assertEqual(self.provider.totalTexts, before + 1)
        chunks = self.service.listChunks(self.tenantId, self.sourceId)
        self.assertEqual([chunk.ordinal for chunk in chunks], [0, 1, 2, 3])
        self.assertTrue(chunks[0].text.startswith("Line three exceeded"))

    def testRemovedParagraphDropsItsChunkAndVector(self) -> None:
        result = self.service.ingestSource(
            self.tenantId, self.command(f"{PARAGRAPH_ONE}\n\n{PARAGRAPH_TWO}")
        )
        self.assertEqual(result.chunksRemoved, 1)
        self.assertEqual(result.embeddingsDeleted, 1)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 2)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 2)

    def testEditedParagraphReplacesOnlyThatChunk(self) -> None:
        edited = DOCUMENT.replace("ninety two percent", "eighty seven percent")
        result = self.service.ingestSource(self.tenantId, self.command(edited))
        self.assertEqual(result.chunksAdded, 1)
        self.assertEqual(result.chunksRemoved, 1)
        self.assertEqual(result.chunksReused, 2)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 3)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 3)

    def testCosmeticEditsAreNotEvenAReindex(self) -> None:
        noisy = DOCUMENT.replace("\n\n", "\n\n\n").replace(". ", ".  ")
        self.assertTrue(self.service.ingestSource(self.tenantId, self.command(noisy)).isNoop)

    def testForcedRunReindexesWithoutContentChange(self) -> None:
        result = self.service.ingestSource(self.tenantId, self.command(force=True))
        self.assertEqual(result.action, "REINDEX")
        self.assertEqual(result.chunksReused, 3)
        self.assertEqual(result.chunksAdded, 0)
        self.assertEqual(result.source.revision, 2)

    def testPolicyChangeRebuildsTheIndex(self) -> None:
        result = self.service.ingestSource(
            self.tenantId,
            self.command(
                policy=ChunkingPolicy(
                    strategy="SENTENCE", maxTokens=10, overlapTokens=0, minTokens=0
                )
            ),
        )
        self.assertEqual(result.action, "REINDEX")
        self.assertGreater(result.chunksAdded, 0)
        self.assertEqual(
            self.service.describeSource(self.tenantId, self.sourceId).policySignature,
            "SENTENCE|10|0|0",
        )

    def testReindexHelperUsesTheStoredIdentity(self) -> None:
        result = self.service.reindexSource(
            self.tenantId, self.sourceId, f"{DOCUMENT}\n\n{PARAGRAPH_FOUR}"
        )
        self.assertEqual(result.action, "REINDEX")
        self.assertEqual(result.source.sourceId, self.sourceId)
        self.assertEqual(result.chunksAdded, 1)

    def testSearchFindsTheReindexedContent(self) -> None:
        self.service.ingestSource(self.tenantId, self.command(f"{DOCUMENT}\n\n{PARAGRAPH_FOUR}"))
        found = self.embedding.searchSimilar(
            self.tenantId,
            SimilaritySearchQuery(spaceCode="KNOWLEDGE_SPACE", queryText=PARAGRAPH_FOUR, topK=1),
        )
        self.assertEqual(len(found.matches), 1)
        resolved = self.service.resolveChunks(
            self.tenantId, [match.sourceId for match in found.matches]
        )
        self.assertEqual(len(resolved), 1)
        self.assertIn("Line three exceeded", resolved[0].text)


class FailureAndLifecycleTests(KnowledgeTestCase):
    def testFailedEmbeddingLeavesTheSourceInFailed(self) -> None:
        service = self.buildService(embedder=ExplodingEmbedder())
        with self.assertRaises(AIKnowledgeIngestionFailed):
            service.ingestSource(self.tenantId, self.command())
        stored = self.service.findSource(self.tenantId, "DOCUMENTS", "DOCUMENT", "doc-1")
        self.assertEqual(stored.status, "FAILED")
        self.assertEqual(stored.revision, 0)
        self.assertTrue(stored.errorCode)

    def testAFailedSourceCanBeIngestedAgain(self) -> None:
        service = self.buildService(embedder=ExplodingEmbedder())
        with self.assertRaises(AIKnowledgeIngestionFailed):
            service.ingestSource(self.tenantId, self.command())
        recovered = self.service.ingestSource(self.tenantId, self.command())
        self.assertEqual(recovered.source.status, "READY")
        self.assertEqual(recovered.source.revision, 1)

    def testMissingEmbedderWithAutoEmbedFailsClosed(self) -> None:
        service = self.buildService(embedder=None)
        with self.assertRaises(AIKnowledgeIngestionFailed):
            service.ingestSource(self.tenantId, self.command())

    def testArchivingDropsChunksAndVectorsButKeepsTheTombstone(self) -> None:
        created = self.service.ingestSource(self.tenantId, self.command())
        archived = self.service.archiveSource(self.tenantId, created.source.sourceId)
        self.assertEqual(archived.status, "ARCHIVED")
        self.assertEqual(archived.chunkCount, 0)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 0)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 0)
        self.assertEqual(AIKnowledgeSourceModel.objects.count(), 1)
        self.assertIn(AUDIT_KNOWLEDGE_ARCHIVED, self.auditActions())

    def testArchivedSourceCannotBeReingested(self) -> None:
        created = self.service.ingestSource(self.tenantId, self.command())
        self.service.archiveSource(self.tenantId, created.source.sourceId)
        with self.assertRaises(AIKnowledgeSourceArchived):
            self.service.ingestSource(self.tenantId, self.command())

    def testDeletingASourceRemovesEverything(self) -> None:
        created = self.service.ingestSource(self.tenantId, self.command())
        removed = self.service.deleteSource(self.tenantId, created.source.sourceId)
        self.assertEqual(removed, 3)
        self.assertEqual(AIKnowledgeSourceModel.objects.count(), 0)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 0)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 0)
        self.assertIn(AUDIT_KNOWLEDGE_PURGED, self.auditActions())

    def testRetentionOnlyPurgesArchivedSources(self) -> None:
        created = self.service.ingestSource(self.tenantId, self.command())
        self.assertEqual(self.service.purgeKnowledgeRetention(self.tenantId, retentionDays=1), 0)
        self.service.archiveSource(self.tenantId, created.source.sourceId)
        future = CLOCK + timedelta(days=900)
        self.assertEqual(self.service.purgeKnowledgeRetention(self.tenantId, now=future), 1)
        self.assertEqual(AIKnowledgeSourceModel.objects.count(), 0)

    def testRetentionRejectsAnImpossibleHorizon(self) -> None:
        with self.assertRaises(AIConfigurationError):
            self.service.purgeKnowledgeRetention(self.tenantId, retentionDays=0)

    def testAuditChainStaysVerifiable(self) -> None:
        created = self.service.ingestSource(self.tenantId, self.command())
        self.service.ingestSource(self.tenantId, self.command(f"{DOCUMENT}\n\n{PARAGRAPH_FOUR}"))
        self.service.archiveSource(self.tenantId, created.source.sourceId)
        actions = self.auditActions()
        self.assertIn(AUDIT_KNOWLEDGE_INGESTED, actions)
        self.assertIn(AUDIT_KNOWLEDGE_REINDEXED, actions)
        self.assertEqual(self.audit.verifyTenantChain(self.tenantId), len(actions))


class ReadAndIsolationTests(KnowledgeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.created = self.service.ingestSource(self.tenantId, self.command())

    def testSourcesCanBeListedAndFiltered(self) -> None:
        self.service.ingestSource(
            self.tenantId,
            self.command(sourceDomain="MEETINGS", sourceEntityType="MEETING", sourceEntityId="m-1"),
        )
        allSources = self.service.listSources(self.tenantId)
        self.assertEqual(len(allSources), 2)
        meetings = self.service.listSources(self.tenantId, sourceDomain="MEETINGS")
        self.assertEqual([item.sourceEntityId for item in meetings], ["m-1"])
        ready = self.service.listSources(self.tenantId, statuses=("READY",))
        self.assertEqual(len(ready), 2)

    def testUnknownSourceAndChunkAreNotFound(self) -> None:
        with self.assertRaises(AIKnowledgeSourceNotFound):
            self.service.describeSource(self.tenantId, uuid.uuid4())
        with self.assertRaises(AIKnowledgeSourceNotFound):
            self.service.findSource(self.tenantId, "DOCUMENTS", "DOCUMENT", "missing")
        with self.assertRaises(AIKnowledgeChunkNotFound):
            self.service.describeChunk(self.tenantId, uuid.uuid4())

    def testChunkResolutionSkipsUnknownIdentifiers(self) -> None:
        chunks = self.service.listChunks(self.tenantId, self.created.source.sourceId)
        resolved = self.service.resolveChunks(
            self.tenantId, [str(chunks[0].chunkId), str(uuid.uuid4()), "not-a-uuid"]
        )
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0].chunkId, chunks[0].chunkId)

    def testDescribeChunkReturnsItsText(self) -> None:
        chunks = self.service.listChunks(self.tenantId, self.created.source.sourceId)
        descriptor = self.service.describeChunk(self.tenantId, chunks[1].chunkId)
        self.assertEqual(descriptor.ordinal, 1)
        self.assertTrue(descriptor.text)
        self.assertEqual(len(descriptor.checksum), 64)

    def testEverythingIsTenantScoped(self) -> None:
        self.assertEqual(self.service.listSources(self.otherTenantId), ())
        with self.assertRaises(AIKnowledgeSourceNotFound):
            self.service.describeSource(self.otherTenantId, self.created.source.sourceId)
        with self.assertRaises(AIKnowledgeSourceNotFound):
            self.service.deleteSource(self.otherTenantId, self.created.source.sourceId)
        self.assertEqual(
            self.service.resolveChunks(
                self.otherTenantId,
                [
                    chunk.chunkId
                    for chunk in self.service.listChunks(
                        self.tenantId, self.created.source.sourceId
                    )
                ],
            ),
            (),
        )

    def testTwoTenantsMayIndexTheSameBusinessRow(self) -> None:
        self.embedding.defineVectorSpace(
            self.otherTenantId,
            DefineVectorSpaceCommand(
                code="KNOWLEDGE_SPACE",
                modelCode="TEXT_EMBED_3",
                dimensions=4,
                providerCode="LOCAL",
            ),
        )
        other = self.service.ingestSource(self.otherTenantId, self.command())
        self.assertEqual(other.source.tenantId, self.otherTenantId)
        self.assertEqual(AIKnowledgeSourceModel.objects.count(), 2)


class KnowledgeJobHandlerTests(KnowledgeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.queue = QueueApplicationService(
            DjangoJobStore(),
            auditService=self.audit,
            queueSettings=QueueSettings(enabled=True, defaultMaxAttempts=2, claimLimit=5),
            workerId="testWorker",
            now=lambda: CLOCK,
        )
        self.queue.registerHandler(KnowledgeIngestionJobHandler(self.service))

    def testAsyncIngestionRunsEndToEnd(self) -> None:
        descriptor = self.queue.submitJob(
            SubmitJobCommand(
                tenantId=self.tenantId,
                kind="INDEXING",
                payload={
                    "sourceDomain": "DOCUMENTS",
                    "sourceEntityType": "DOCUMENT",
                    "sourceEntityId": "async-1",
                    "title": "Async report",
                    "content": DOCUMENT,
                    "spaceCode": "KNOWLEDGE_SPACE",
                },
            )
        )
        report = self.queue.runOnce()
        self.assertEqual(report.succeeded, 1)
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "SUCCEEDED")
        self.assertEqual(settled.resultSummary["action"], "CREATE")
        self.assertEqual(settled.resultSummary["chunksAdded"], 3)
        self.assertEqual(settled.resultSummary["embeddingsCreated"], 3)
        self.assertEqual(AIKnowledgeChunkRecordModel.objects.count(), 3)

    def testInvalidPayloadFailsTheJobNotTheWorker(self) -> None:
        descriptor = self.queue.submitJob(
            SubmitJobCommand(
                tenantId=self.tenantId, kind="INDEXING", payload={"title": "no content"}
            )
        )
        self.queue.runOnce()
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.errorCode, "AI_KNOWLEDGE_SOURCE_INVALID")

    def testHandlerAdvertisesItsKind(self) -> None:
        self.assertEqual(KnowledgeIngestionJobHandler(self.service).kind(), "INDEXING")


class ClassificationPropagationTests(KnowledgeTestCase):
    """A downgrade must reach chunks that survive a reindex by checksum."""

    def testReusedChunksInheritTheNewClassification(self) -> None:
        created = self.service.ingestSource(self.tenantId, self.command())
        self.assertEqual(
            {
                chunk.classification
                for chunk in self.service.listChunks(self.tenantId, created.source.sourceId)
            },
            {"INTERNAL"},
        )
        result = self.service.ingestSource(
            self.tenantId, self.command(classification="RESTRICTED", force=True)
        )
        self.assertEqual(result.chunksReused, 3)
        self.assertEqual(
            {
                chunk.classification
                for chunk in self.service.listChunks(self.tenantId, created.source.sourceId)
            },
            {"RESTRICTED"},
        )

    def testUnchangedClassificationDoesNotTouchChunks(self) -> None:
        created = self.service.ingestSource(self.tenantId, self.command())
        self.service.ingestSource(self.tenantId, self.command(force=True))
        self.assertEqual(
            {
                chunk.classification
                for chunk in self.service.listChunks(self.tenantId, created.source.sourceId)
            },
            {"INTERNAL"},
        )
