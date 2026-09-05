"""Phase 13-Q application tests — embedding foundation over a real SQLite DB.

Covers vector space administration (definition, duplicate protection,
listing, deactivation), embedding writes through a scripted provider
(creation, fingerprint cache reuse, replacement, provider-contract
violations), similarity search (vector query, text query, filters, top-K,
minimum score), tenant isolation, the fail-closed switch, metering
attribution through the Phase 13-N port, audit entries in the real
Phase 13-O ledger, deletion/retention, and the Phase 13-P
``EMBEDDING`` job handler end-to-end (submit → worker → stored vectors).

Persistence is the real ``DjangoVectorSpaceStore``/``DjangoEmbeddingStore``
and the real Django audit stores; only the provider and the metering
recorder are doubles, because Q must not call a vendor or re-test N.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from django.test import TestCase

from apps.ai.application.services.auditService import AuditApplicationService, AuditSettings
from apps.ai.application.services.embeddingService import (
    AUDIT_EMBEDDING_CREATED,
    AUDIT_EMBEDDING_DELETED,
    AUDIT_SPACE_DEACTIVATED,
    AUDIT_SPACE_DEFINED,
    DefineVectorSpaceCommand,
    EmbeddingApplicationService,
    EmbeddingJobHandler,
    EmbeddingSettings,
    EmbedTextsCommand,
    SimilaritySearchQuery,
    UsageAttribution,
)
from apps.ai.application.services.queueService import (
    QueueApplicationService,
    QueueSettings,
    SubmitJobCommand,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIEmbeddingBatchTooLarge,
    AIEmbeddingInvalid,
    AIEmbeddingNotFound,
    AIVectorSpaceAlreadyRegistered,
    AIVectorSpaceInactive,
    AIVectorSpaceMismatch,
    AIVectorSpaceNotFound,
)
from apps.ai.domain.services.embeddingEngine import EmbeddingItem
from apps.ai.domain.valueObjects.embeddingTypes import VectorSpace, isUnitVector
from apps.ai.infrastructure.models import AIStoredEmbeddingModel
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)
from apps.ai.infrastructure.repositories.embeddingRepositories import (
    DjangoEmbeddingStore,
    DjangoVectorSpaceStore,
)
from apps.ai.infrastructure.repositories.queueRepositories import DjangoJobStore
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class ScriptedProvider:
    """Offline embedding provider double with a deterministic geometry.

    Vectors are chosen by keyword so tests can reason about similarity
    without depending on any real model: ``kpi`` → x-axis, ``budget`` →
    y-axis, anything else → z-axis.
    """

    def __init__(self, dimensions: int = 4) -> None:
        self.dimensions = dimensions
        self.embedCalls: list[str] = []
        self.batchCalls: list[list[str]] = []
        self.forcedVector: list[float] | None = None
        self.forcedCount: int | None = None

    def vectorFor(self, text: str) -> list[float]:
        if self.forcedVector is not None:
            return list(self.forcedVector)
        lowered = text.lower()
        base = [0.0] * self.dimensions
        if "kpi" in lowered:
            base[0] = 1.0
        elif "budget" in lowered:
            base[1] = 1.0
        else:
            base[2] = 1.0
        base[self.dimensions - 1] = 0.25
        return base

    def embed(self, *, text: str, model: str, **kwargs: Any) -> list[float]:
        self.embedCalls.append(text)
        return self.vectorFor(text)

    def embedBatch(self, *, texts: Any, model: str, **kwargs: Any) -> list[list[float]]:
        materialized = list(texts)
        self.batchCalls.append(materialized)
        vectors = [self.vectorFor(text) for text in materialized]
        if self.forcedCount is not None:
            return vectors[: self.forcedCount]
        return vectors

    @property
    def totalCalls(self) -> int:
        return len(self.embedCalls) + len(self.batchCalls)


class FixedResolver:
    def __init__(self, provider: ScriptedProvider) -> None:
        self.provider = provider
        self.resolved: list[str] = []

    def providerFor(self, tenantId: uuid.UUID, space: VectorSpace) -> ScriptedProvider:
        self.resolved.append(space.code)
        return self.provider


class RecordingUsageRecorder:
    """Captures what Q hands to the Phase 13-N application service."""

    def __init__(self) -> None:
        self.calls: list[tuple[uuid.UUID, Any]] = []

    def recordProviderAttempt(self, tenantId: Any, command: Any, **kwargs: Any) -> Any:
        self.calls.append((tenantId, command))
        return command


class EmbeddingApplicationTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.provider = ScriptedProvider()
        self.resolver = FixedResolver(self.provider)
        self.usage = RecordingUsageRecorder()
        self.spaceStore = DjangoVectorSpaceStore()
        self.embeddingStore = DjangoEmbeddingStore(self.spaceStore)
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=AuditSettings(enabled=True, retentionDays=365),
            now=lambda: CLOCK,
        )
        self.service = self.buildService()

    def buildService(self, **settingsOverrides: Any) -> EmbeddingApplicationService:
        settings = EmbeddingSettings(
            enabled=settingsOverrides.pop("enabled", True),
            maxBatchSize=settingsOverrides.pop("maxBatchSize", 2),
            maxInputTokens=settingsOverrides.pop("maxInputTokens", 4096),
            cacheEnabled=settingsOverrides.pop("cacheEnabled", True),
            searchCandidateLimit=settingsOverrides.pop("searchCandidateLimit", 100),
            retentionDays=settingsOverrides.pop("retentionDays", 365),
        )
        return EmbeddingApplicationService(
            self.spaceStore,
            self.embeddingStore,
            providerResolver=self.resolver,
            settings=settings,
            usageRecorder=self.usage,
            auditLogger=self.audit,
            now=lambda: CLOCK,
        )

    def defineSpace(self, code: str = "KPI_SPACE", **overrides: Any) -> Any:
        command = DefineVectorSpaceCommand(
            code=code,
            modelCode=overrides.pop("modelCode", "TEXT_EMBED_3"),
            dimensions=overrides.pop("dimensions", 4),
            providerCode=overrides.pop("providerCode", "LOCAL"),
            **overrides,
        )
        return self.service.defineVectorSpace(self.tenantId, command)

    def items(self, *texts: str) -> tuple[EmbeddingItem, ...]:
        return tuple(
            EmbeddingItem(text=text, sourceType="KNOWLEDGE_CHUNK", sourceId=f"chunk-{index}")
            for index, text in enumerate(texts)
        )

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class VectorSpaceAdministrationTests(EmbeddingApplicationTestCase):
    def testDefiningASpacePersistsItAndAuditsTheDecision(self) -> None:
        descriptor = self.defineSpace()
        self.assertEqual(descriptor.code, "KPI_SPACE")
        self.assertEqual(descriptor.dimensions, 4)
        self.assertEqual(descriptor.metric, "COSINE")
        self.assertEqual(descriptor.normalization, "L2")
        self.assertTrue(descriptor.isActive)
        self.assertIn(AUDIT_SPACE_DEFINED, self.auditActions())

    def testDuplicateSpaceCodeIsRejected(self) -> None:
        self.defineSpace()
        with self.assertRaises(AIVectorSpaceAlreadyRegistered):
            self.defineSpace()

    def testUnknownSpaceIsNotFound(self) -> None:
        with self.assertRaises(AIVectorSpaceNotFound):
            self.service.describeVectorSpace(self.tenantId, "MISSING_SPACE")

    def testListingIsSortedAndCanFilterInactiveSpaces(self) -> None:
        self.defineSpace("ZULU_SPACE")
        self.defineSpace("ALPHA_SPACE")
        codes = [item.code for item in self.service.listVectorSpaces(self.tenantId)]
        self.assertEqual(codes, ["ALPHA_SPACE", "ZULU_SPACE"])
        self.service.deactivateVectorSpace(self.tenantId, "ZULU_SPACE")
        active = [
            item.code for item in self.service.listVectorSpaces(self.tenantId, activeOnly=True)
        ]
        self.assertEqual(active, ["ALPHA_SPACE"])

    def testDeactivationBlocksWritesButNotReads(self) -> None:
        self.defineSpace()
        self.service.embedTexts(
            self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend"))
        )
        self.service.deactivateVectorSpace(self.tenantId, "KPI_SPACE")
        self.assertIn(AUDIT_SPACE_DEACTIVATED, self.auditActions())
        with self.assertRaises(AIVectorSpaceInactive):
            self.service.embedTexts(
                self.tenantId,
                EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("budget plan")),
            )
        result = self.service.searchSimilar(
            self.tenantId,
            SimilaritySearchQuery(spaceCode="KPI_SPACE", queryVector=(1.0, 0.0, 0.0, 0.25)),
        )
        self.assertEqual(len(result.matches), 1)
        self.service.activateVectorSpace(self.tenantId, "KPI_SPACE")
        self.assertTrue(self.service.describeVectorSpace(self.tenantId, "KPI_SPACE").isActive)

    def testSpacesAreTenantScoped(self) -> None:
        self.defineSpace()
        with self.assertRaises(AIVectorSpaceNotFound):
            self.service.describeVectorSpace(self.otherTenantId, "KPI_SPACE")
        self.assertEqual(self.service.listVectorSpaces(self.otherTenantId), ())


class EmbeddingWriteTests(EmbeddingApplicationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.defineSpace()

    def testEmbeddingStoresNormalizedVectorsAndAudits(self) -> None:
        result = self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend", "budget plan")),
        )
        self.assertEqual(len(result.created), 2)
        self.assertEqual(result.reused, ())
        self.assertEqual(result.providerCalls, 1)
        rows = AIStoredEmbeddingModel.objects.filter(tenantId=self.tenantId)
        self.assertEqual(rows.count(), 2)
        for row in rows:
            self.assertTrue(isUnitVector(tuple(row.vector)))
            self.assertEqual(row.dimensions, 4)
            self.assertEqual(len(row.contentHash), 64)
        self.assertIn(AUDIT_EMBEDDING_CREATED, self.auditActions())

    def testBatchesRespectTheConfiguredCeiling(self) -> None:
        self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(
                spaceCode="KPI_SPACE",
                items=self.items("kpi one", "budget two", "other three"),
            ),
        )
        # maxBatchSize=2 splits three items into a batch of two plus a
        # remainder; a single-text step uses the provider's ``embed`` entry
        # point rather than a one-element batch call.
        self.assertEqual([len(call) for call in self.provider.batchCalls], [2])
        self.assertEqual(self.provider.embedCalls, ["other three"])
        self.assertEqual(self.service.countEmbeddings(self.tenantId, "KPI_SPACE"), 3)

    def testRepeatedTextIsServedFromTheFingerprintCache(self) -> None:
        first = self.service.embedTexts(
            self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend"))
        )
        callsAfterFirst = self.provider.totalCalls
        second = self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("  kpi   trend ")),
        )
        self.assertEqual(len(first.created), 1)
        self.assertEqual(second.created, ())
        self.assertEqual(len(second.reused), 1)
        self.assertEqual(self.provider.totalCalls, callsAfterFirst)
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 1)

    def testDuplicateTextsInsideOneCallAreEmbeddedOnce(self) -> None:
        items = (
            EmbeddingItem(text="kpi trend", sourceType="DOCUMENT", sourceId="a"),
            EmbeddingItem(text="kpi trend", sourceType="DOCUMENT", sourceId="b"),
        )
        result = self.service.embedTexts(
            self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=items)
        )
        self.assertEqual(result.duplicates, 1)
        self.assertEqual(len(result.created), 1)

    def testCacheCanBeBypassedWithoutCreatingADuplicateRow(self) -> None:
        self.service.embedTexts(
            self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend"))
        )
        self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend"), useCache=False),
        )
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 1)

    def testReplaceExistingDropsThePreviousVectorsOfThatSource(self) -> None:
        item = EmbeddingItem(text="kpi trend", sourceType="DOCUMENT", sourceId="doc-1")
        self.service.embedTexts(
            self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=(item,))
        )
        replacement = EmbeddingItem(text="budget plan", sourceType="DOCUMENT", sourceId="doc-1")
        self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(spaceCode="KPI_SPACE", items=(replacement,), replaceExisting=True),
        )
        stored = self.service.listSourceEmbeddings(self.tenantId, "KPI_SPACE", "DOCUMENT", "doc-1")
        self.assertEqual(len(stored), 1)
        self.assertEqual(
            stored[0].contentHash,
            replacement.fingerprint(
                VectorSpace(code="KPI_SPACE", modelCode="TEXT_EMBED_3", dimensions=4)
            ),
        )

    def testProviderDimensionalityIsVerifiedBeforePersistence(self) -> None:
        self.provider.forcedVector = [1.0, 0.0]
        with self.assertRaises(AIVectorSpaceMismatch):
            self.service.embedTexts(
                self.tenantId,
                EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend")),
            )
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 0)

    def testProviderReturningFewerVectorsFailsTheWholeBatch(self) -> None:
        self.provider.forcedCount = 1
        with self.assertRaises(AIEmbeddingInvalid):
            self.service.embedTexts(
                self.tenantId,
                EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi one", "budget two")),
            )
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), 0)

    def testEmptyCommandAndWrongTypesAreRejected(self) -> None:
        with self.assertRaises(AIEmbeddingInvalid):
            self.service.embedTexts(
                self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=())
            )
        with self.assertRaises(AIEmbeddingInvalid):
            self.service.embedTexts(self.tenantId, "embed please")  # type: ignore[arg-type]

    def testMissingProviderResolverFailsClosed(self) -> None:
        service = EmbeddingApplicationService(
            self.spaceStore,
            self.embeddingStore,
            providerResolver=None,
            settings=EmbeddingSettings(),
            now=lambda: CLOCK,
        )
        with self.assertRaises(AIConfigurationError):
            service.embedTexts(
                self.tenantId,
                EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend")),
            )

    def testDisabledFoundationRefusesReadsAndWrites(self) -> None:
        disabled = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            disabled.embedTexts(
                self.tenantId,
                EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend")),
            )
        with self.assertRaises(AIConfigurationError):
            disabled.listVectorSpaces(self.tenantId)

    def testEmbeddingsAreTenantScoped(self) -> None:
        self.service.embedTexts(
            self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend"))
        )
        with self.assertRaises(AIVectorSpaceNotFound):
            self.service.embedTexts(
                self.otherTenantId,
                EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend")),
            )
        self.assertEqual(self.service.countEmbeddings(self.tenantId, "KPI_SPACE"), 1)


class MeteringAndAuditTests(EmbeddingApplicationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.defineSpace()

    def attribution(self) -> UsageAttribution:
        return UsageAttribution(
            requestId=uuid.uuid4(),
            modelId=uuid.uuid4(),
            providerId=uuid.uuid4(),
            providerCode="LOCAL",
            modelCode="TEXT_EMBED_3",
            correlationId="corr-1",
            traceId="trace-1",
        )

    def testAttributedCallIsMeteredThroughThePhase13NCommand(self) -> None:
        attribution = self.attribution()
        self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(
                spaceCode="KPI_SPACE",
                items=self.items("kpi trend"),
                attribution=attribution,
            ),
        )
        self.assertEqual(len(self.usage.calls), 1)
        tenant, command = self.usage.calls[0]
        self.assertEqual(tenant, self.tenantId)
        self.assertEqual(command.requestId, attribution.requestId)
        self.assertEqual(command.modelId, attribution.modelId)
        self.assertEqual(command.providerId, attribution.providerId)
        self.assertEqual(command.capabilityCode, "EMBEDDING")
        self.assertEqual(command.outputTokens, 0)
        self.assertGreater(command.inputTokens, 0)
        self.assertEqual(command.correlationId, "corr-1")

    def testUnattributedCallIsNotMeteredRatherThanFaked(self) -> None:
        self.service.embedTexts(
            self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend"))
        )
        self.assertEqual(self.usage.calls, [])

    def testStoredVectorCarriesTheAttributedModelIdentity(self) -> None:
        attribution = self.attribution()
        result = self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(
                spaceCode="KPI_SPACE", items=self.items("kpi trend"), attribution=attribution
            ),
        )
        row = AIStoredEmbeddingModel.objects.get(id=result.created[0].embeddingId)
        self.assertEqual(row.modelId, attribution.modelId)
        self.assertEqual(row.providerCode, "LOCAL")

    def testAuditChainStaysVerifiableAfterQEntries(self) -> None:
        self.service.embedTexts(
            self.tenantId, EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend"))
        )
        self.service.deleteSourceEmbeddings(
            self.tenantId, "KPI_SPACE", "KNOWLEDGE_CHUNK", "chunk-0"
        )
        actions = self.auditActions()
        self.assertIn(AUDIT_SPACE_DEFINED, actions)
        self.assertIn(AUDIT_EMBEDDING_CREATED, actions)
        self.assertIn(AUDIT_EMBEDDING_DELETED, actions)
        self.assertEqual(self.audit.verifyTenantChain(self.tenantId), len(actions))

    def testAuditIsOptionalAndItsAbsenceIsNotFatal(self) -> None:
        service = EmbeddingApplicationService(
            self.spaceStore,
            self.embeddingStore,
            providerResolver=self.resolver,
            settings=EmbeddingSettings(maxBatchSize=2),
            now=lambda: CLOCK,
        )
        result = service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("budget plan")),
        )
        self.assertEqual(len(result.created), 1)


class SimilaritySearchTests(EmbeddingApplicationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.defineSpace()
        self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(
                spaceCode="KPI_SPACE",
                items=(
                    EmbeddingItem(text="kpi trend", sourceType="DOCUMENT", sourceId="kpi-doc"),
                    EmbeddingItem(
                        text="budget plan", sourceType="KNOWLEDGE_CHUNK", sourceId="budget-chunk"
                    ),
                    EmbeddingItem(text="other note", sourceType="MESSAGE", sourceId="note-1"),
                ),
            ),
        )

    def testVectorQueryRanksWithoutCallingTheProvider(self) -> None:
        before = self.provider.totalCalls
        result = self.service.searchSimilar(
            self.tenantId,
            SimilaritySearchQuery(spaceCode="KPI_SPACE", queryVector=(1.0, 0.0, 0.0, 0.25), topK=2),
        )
        self.assertFalse(result.usedQueryEmbedding)
        self.assertEqual(self.provider.totalCalls, before)
        self.assertEqual(result.matches[0].sourceId, "kpi-doc")
        self.assertEqual(len(result.matches), 2)

    def testTextQueryEmbedsTheQuestionWithoutStoringIt(self) -> None:
        countBefore = AIStoredEmbeddingModel.objects.count()
        result = self.service.searchSimilar(
            self.tenantId,
            SimilaritySearchQuery(spaceCode="KPI_SPACE", queryText="what is the kpi?", topK=1),
        )
        self.assertTrue(result.usedQueryEmbedding)
        self.assertEqual(result.matches[0].sourceId, "kpi-doc")
        self.assertEqual(AIStoredEmbeddingModel.objects.count(), countBefore)

    def testSourceTypeFilterNarrowsTheCandidateSet(self) -> None:
        result = self.service.searchSimilar(
            self.tenantId,
            SimilaritySearchQuery(
                spaceCode="KPI_SPACE",
                queryVector=(1.0, 0.0, 0.0, 0.25),
                sourceTypes=("KNOWLEDGE_CHUNK",),
                topK=5,
            ),
        )
        self.assertEqual(result.scanned, 1)
        self.assertEqual([match.sourceId for match in result.matches], ["budget-chunk"])

    def testMinimumScoreDropsWeakMatches(self) -> None:
        result = self.service.searchSimilar(
            self.tenantId,
            SimilaritySearchQuery(
                spaceCode="KPI_SPACE",
                queryVector=(1.0, 0.0, 0.0, 0.25),
                topK=5,
                minScore=0.9,
            ),
        )
        self.assertEqual([match.sourceId for match in result.matches], ["kpi-doc"])

    def testCandidateLimitBoundsTheScan(self) -> None:
        result = self.service.searchSimilar(
            self.tenantId,
            SimilaritySearchQuery(
                spaceCode="KPI_SPACE", queryVector=(1.0, 0.0, 0.0, 0.25), candidateLimit=2
            ),
        )
        self.assertEqual(result.scanned, 2)

    def testSearchRequiresAQueryAndAPositiveTopK(self) -> None:
        with self.assertRaises(AIEmbeddingInvalid):
            self.service.searchSimilar(self.tenantId, SimilaritySearchQuery(spaceCode="KPI_SPACE"))
        with self.assertRaises(AIEmbeddingInvalid):
            self.service.searchSimilar(
                self.tenantId,
                SimilaritySearchQuery(
                    spaceCode="KPI_SPACE", queryVector=(1.0, 0.0, 0.0, 0.25), topK=0
                ),
            )

    def testQueryVectorOfTheWrongShapeIsRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.service.searchSimilar(
                self.tenantId,
                SimilaritySearchQuery(spaceCode="KPI_SPACE", queryVector=(1.0, 0.0)),
            )

    def testSearchNeverCrossesTenantBoundaries(self) -> None:
        with self.assertRaises(AIVectorSpaceNotFound):
            self.service.searchSimilar(
                self.otherTenantId,
                SimilaritySearchQuery(spaceCode="KPI_SPACE", queryVector=(1.0, 0.0, 0.0, 0.25)),
            )


class LifecycleTests(EmbeddingApplicationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.defineSpace()
        self.result = self.service.embedTexts(
            self.tenantId,
            EmbedTextsCommand(spaceCode="KPI_SPACE", items=self.items("kpi trend", "budget plan")),
        )

    def testDescribeEmbeddingReturnsASafeReadModel(self) -> None:
        descriptor = self.service.describeEmbedding(
            self.tenantId, self.result.created[0].embeddingId
        )
        self.assertEqual(descriptor.spaceCode, "KPI_SPACE")
        self.assertEqual(descriptor.dimensions, 4)
        self.assertFalse(hasattr(descriptor, "vector"))

    def testDescribeEmbeddingIsTenantScoped(self) -> None:
        with self.assertRaises(AIEmbeddingNotFound):
            self.service.describeEmbedding(self.otherTenantId, self.result.created[0].embeddingId)

    def testDeletingASourceRemovesOnlyThatSource(self) -> None:
        removed = self.service.deleteSourceEmbeddings(
            self.tenantId, "KPI_SPACE", "KNOWLEDGE_CHUNK", "chunk-0"
        )
        self.assertEqual(removed, 1)
        self.assertEqual(self.service.countEmbeddings(self.tenantId, "KPI_SPACE"), 1)

    def testPurgingASpaceRemovesEverythingInIt(self) -> None:
        self.assertEqual(self.service.purgeVectorSpace(self.tenantId, "KPI_SPACE"), 2)
        self.assertEqual(self.service.countEmbeddings(self.tenantId, "KPI_SPACE"), 0)

    def testRetentionPurgeHonoursTheCutoffAndConfiguration(self) -> None:
        self.assertEqual(self.service.purgeEmbeddingRetention(self.tenantId, retentionDays=365), 0)
        future = CLOCK + timedelta(days=800)
        self.assertEqual(self.service.purgeEmbeddingRetention(self.tenantId, now=future), 2)
        with self.assertRaises(AIConfigurationError):
            self.service.purgeEmbeddingRetention(self.tenantId, retentionDays=0)


class EmbeddingJobHandlerTests(EmbeddingApplicationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.defineSpace()
        self.queue = QueueApplicationService(
            DjangoJobStore(),
            auditService=self.audit,
            queueSettings=QueueSettings(enabled=True, defaultMaxAttempts=2, claimLimit=5),
            workerId="testWorker",
            now=lambda: CLOCK,
        )
        self.queue.registerHandler(EmbeddingJobHandler(self.service))

    def submit(self, payload: dict[str, Any]) -> Any:
        return self.queue.submitJob(
            SubmitJobCommand(tenantId=self.tenantId, kind="EMBEDDING", payload=payload)
        )

    def testAsyncEmbeddingRunsEndToEnd(self) -> None:
        descriptor = self.submit(
            {
                "spaceCode": "KPI_SPACE",
                "items": [
                    {"text": "kpi trend", "sourceType": "DOCUMENT", "sourceId": "doc-1"},
                    {"text": "budget plan", "sourceType": "DOCUMENT", "sourceId": "doc-2"},
                ],
            }
        )
        report = self.queue.runOnce()
        self.assertEqual(report.succeeded, 1)
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "SUCCEEDED")
        self.assertEqual(settled.resultSummary["created"], 2)
        self.assertEqual(self.service.countEmbeddings(self.tenantId, "KPI_SPACE"), 2)

    def testJobPayloadValidationFailsTheJobNotTheWorker(self) -> None:
        descriptor = self.submit({"spaceCode": "KPI_SPACE", "items": []})
        self.queue.runOnce()
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertIn(settled.status, {"PENDING", "FAILED", "DEAD"})
        self.assertEqual(settled.errorCode, "AI_EMBEDDING_INVALID")

    def testHandlerRejectsAnOversizedPayloadDirectly(self) -> None:
        handler = EmbeddingJobHandler(self.service)

        class FakeJob:
            tenantId = self.tenantId
            payload = {
                "spaceCode": "KPI_SPACE",
                "items": [{"text": f"t{index}", "sourceId": str(index)} for index in range(600)],
            }

        with self.assertRaises(AIEmbeddingBatchTooLarge):
            handler.execute(FakeJob())

    def testHandlerAdvertisesItsKind(self) -> None:
        self.assertEqual(EmbeddingJobHandler(self.service).kind(), "EMBEDDING")
