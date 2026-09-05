"""Phase 13-Q unit tests — embedding foundation, fully offline.

Covers the closed vocabularies and vector math, the ``VectorSpace``
identity invariant, the two entities and their guards, the planning
engine (canonicalization, fingerprint dedupe, cache subtraction, batch
splitting, token budget, absolute ceilings), provider-result validation,
entity construction with normalization, deterministic top-K ranking with
its tie-break, and the Phase 13-B bridge.

No Django, database, network, provider SDK, or clock dependency: every
test uses a fixed clock and pure values.
"""

from __future__ import annotations

import dataclasses
import math
import unittest
import uuid
from datetime import UTC, datetime

from apps.ai.domain.entities.aiRecords import AIEmbedding
from apps.ai.domain.entities.embeddingRecords import (
    MAX_SOURCE_ID_LENGTH,
    AIStoredEmbedding,
    AIVectorSpaceDefinition,
    ensureFingerprint,
    ensureSourceId,
)
from apps.ai.domain.exceptions import (
    AIEmbeddingBatchTooLarge,
    AIEmbeddingInvalid,
    AITokenLimitExceeded,
    AIVectorSpaceMismatch,
)
from apps.ai.domain.services.embeddingEngine import (
    EmbeddingEngine,
    EmbeddingItem,
    SimilarityMatch,
    rankBySimilarity,
)
from apps.ai.domain.valueObjects.embeddingTypes import (
    DISTANCE_METRICS,
    EMBEDDING_SOURCE_TYPES,
    MAX_BATCH_SIZE,
    MAX_VECTOR_DIMENSIONS,
    NORMALIZATION_MODES,
    VectorSpace,
    contentFingerprint,
    cosineSimilarity,
    dotProduct,
    ensureDimensions,
    ensureMetric,
    ensureNormalization,
    ensureSourceType,
    euclideanDistance,
    isUnitVector,
    l2Norm,
    normalizeText,
    normalizeVector,
    similarityFor,
    validateVector,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("11111111-1111-4111-8111-111111111111")
OTHER_TENANT = uuid.UUID("22222222-2222-4222-8222-222222222222")


def space(**overrides: object) -> VectorSpace:
    params: dict = {
        "code": "DEFAULT_SPACE",
        "modelCode": "TEXT_EMBED_3",
        "dimensions": 4,
        "metric": "COSINE",
        "normalization": "L2",
    }
    params.update(overrides)
    return VectorSpace(**params)


def frozenClock() -> datetime:
    return CLOCK


class VocabularyTests(unittest.TestCase):
    def testClosedVocabulariesAreStable(self) -> None:
        self.assertIn("KNOWLEDGE_CHUNK", EMBEDDING_SOURCE_TYPES)
        self.assertIn("QUERY", EMBEDDING_SOURCE_TYPES)
        self.assertEqual(DISTANCE_METRICS, ("COSINE", "DOT_PRODUCT", "EUCLIDEAN"))
        self.assertEqual(NORMALIZATION_MODES, ("NONE", "L2"))

    def testVocabularyValuesAreNormalizedAndValidated(self) -> None:
        self.assertEqual(ensureSourceType(" document "), "DOCUMENT")
        self.assertEqual(ensureMetric("cosine"), "COSINE")
        self.assertEqual(ensureNormalization("l2"), "L2")
        with self.assertRaises(ValidationFailedError):
            ensureSourceType("INVOICE")
        with self.assertRaises(ValidationFailedError):
            ensureMetric("MANHATTAN")

    def testDimensionsAreBoundedAndTyped(self) -> None:
        self.assertEqual(ensureDimensions(1536), 1536)
        for bad in (0, -1, MAX_VECTOR_DIMENSIONS + 1):
            with self.assertRaises(ValidationFailedError):
                ensureDimensions(bad)
        with self.assertRaises(ValidationFailedError):
            ensureDimensions(True)  # bool is not an acceptable dimension

    def testTextCanonicalizationCollapsesWhitespaceAndNormalizesUnicode(self) -> None:
        self.assertEqual(normalizeText("  hello   world \n"), "hello world")
        # NFD "é" and NFC "é" must canonicalize to the same string.
        self.assertEqual(normalizeText("e\u0301te"), normalizeText("\u00e9te"))

    def testFingerprintIsStableCaseSensitiveAndSpaceScoped(self) -> None:
        first = contentFingerprint("Quarterly KPI report", space())
        second = contentFingerprint("  Quarterly   KPI report  ", space())
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertNotEqual(first, contentFingerprint("quarterly kpi report", space()))
        other = contentFingerprint("Quarterly KPI report", space(code="OTHER_SPACE"))
        self.assertNotEqual(first, other)
        with self.assertRaises(ValidationFailedError):
            contentFingerprint("   ", space())


class VectorMathTests(unittest.TestCase):
    def testValidateVectorRejectsEmptyNonFiniteAndWrongArity(self) -> None:
        self.assertEqual(validateVector([1, 2, 3]), (1.0, 2.0, 3.0))
        with self.assertRaises(ValidationFailedError):
            validateVector([])
        with self.assertRaises(ValidationFailedError):
            validateVector([1.0, float("nan")])
        with self.assertRaises(ValidationFailedError):
            validateVector([1.0, float("inf")])
        with self.assertRaises(ValidationFailedError):
            validateVector([1.0, 2.0], dimensions=3)
        with self.assertRaises(ValidationFailedError):
            validateVector(["a", "b"])  # type: ignore[list-item]

    def testNormalizationProducesUnitVectors(self) -> None:
        normalized = normalizeVector([3.0, 4.0])
        self.assertAlmostEqual(l2Norm(normalized), 1.0)
        self.assertTrue(isUnitVector(normalized))
        self.assertAlmostEqual(normalized[0], 0.6)
        self.assertAlmostEqual(normalized[1], 0.8)

    def testZeroVectorCannotBeNormalizedOrCosineCompared(self) -> None:
        with self.assertRaises(ValidationFailedError):
            normalizeVector([0.0, 0.0])
        with self.assertRaises(ValidationFailedError):
            cosineSimilarity([0.0, 0.0], [1.0, 0.0])

    def testMetricsProduceExpectedValues(self) -> None:
        self.assertAlmostEqual(dotProduct([1.0, 2.0], [3.0, 4.0]), 11.0)
        self.assertAlmostEqual(cosineSimilarity([1.0, 0.0], [1.0, 0.0]), 1.0)
        self.assertAlmostEqual(cosineSimilarity([1.0, 0.0], [-1.0, 0.0]), -1.0)
        self.assertAlmostEqual(cosineSimilarity([1.0, 0.0], [0.0, 1.0]), 0.0)
        self.assertAlmostEqual(euclideanDistance([0.0, 0.0], [3.0, 4.0]), 5.0)

    def testCosineIsClampedIntoRange(self) -> None:
        value = cosineSimilarity([1e-8, 0.0], [1e-8, 0.0])
        self.assertLessEqual(value, 1.0)
        self.assertGreaterEqual(value, -1.0)

    def testMismatchedDimensionalityNeverCompares(self) -> None:
        for fn in (dotProduct, cosineSimilarity, euclideanDistance):
            with self.assertRaises(ValidationFailedError):
                fn([1.0, 2.0], [1.0, 2.0, 3.0])

    def testSimilarityForMakesEveryMetricHigherIsBetter(self) -> None:
        near = similarityFor("EUCLIDEAN", [0.0, 0.0], [0.0, 0.1])
        far = similarityFor("EUCLIDEAN", [0.0, 0.0], [0.0, 9.0])
        self.assertGreater(near, far)
        self.assertAlmostEqual(similarityFor("DOT_PRODUCT", [1.0, 1.0], [2.0, 2.0]), 4.0)

    def testScoresAreRoundedForReproducibility(self) -> None:
        score = similarityFor("COSINE", [1.0, 1.0, 0.0], [1.0, 1.0, 1e-17])
        self.assertEqual(score, round(score, 9))


class VectorSpaceTests(unittest.TestCase):
    def testSpaceNormalizesCodesAndExposesSignature(self) -> None:
        subject = VectorSpace(code="kpi_space", modelCode="text_embed_3", dimensions=8)
        self.assertEqual(subject.code, "KPI_SPACE")
        self.assertEqual(subject.modelCode, "TEXT_EMBED_3")
        self.assertEqual(subject.signature(), "KPI_SPACE|TEXT_EMBED_3|-|8|COSINE|L2")
        self.assertTrue(subject.isNormalized)

    def testSpacesDifferingInAnyFacetDoNotMatch(self) -> None:
        base = space()
        self.assertTrue(base.matches(space()))
        self.assertFalse(base.matches(space(dimensions=8)))
        self.assertFalse(base.matches(space(metric="DOT_PRODUCT")))
        self.assertFalse(base.matches(space(normalization="NONE")))
        self.assertFalse(base.matches(space(modelVersion="2024-10")))
        self.assertFalse(base.matches(space(modelCode="OTHER_MODEL")))

    def testPrepareAppliesNormalizationPolicy(self) -> None:
        normalized = space().prepare([3.0, 4.0, 0.0, 0.0])
        self.assertTrue(isUnitVector(normalized))
        raw = space(normalization="NONE").prepare([3.0, 4.0, 0.0, 0.0])
        self.assertEqual(raw, (3.0, 4.0, 0.0, 0.0))

    def testPrepareRejectsWrongDimensionality(self) -> None:
        with self.assertRaises(ValidationFailedError):
            space().prepare([1.0, 2.0])

    def testSpaceScoreUsesItsOwnMetric(self) -> None:
        subject = space(metric="DOT_PRODUCT", normalization="NONE")
        self.assertAlmostEqual(subject.score([1.0, 2.0, 0.0, 0.0], [3.0, 4.0, 0.0, 0.0]), 11.0)


class VectorSpaceDefinitionTests(unittest.TestCase):
    def testDefinitionValidatesAndDefaultsToActive(self) -> None:
        definition = AIVectorSpaceDefinition(tenantId=TENANT, space=space())
        self.assertTrue(definition.isActive)
        self.assertEqual(definition.code, "DEFAULT_SPACE")
        definition.requireWritable()

    def testDeactivationClosesWritesAndStampsTime(self) -> None:
        definition = AIVectorSpaceDefinition(tenantId=TENANT, space=space())
        definition.deactivate(now=CLOCK)
        self.assertFalse(definition.isActive)
        self.assertEqual(definition.updatedAt, CLOCK)
        with self.assertRaises(ValidationFailedError):
            definition.requireWritable()
        definition.activate(now=CLOCK)
        self.assertTrue(definition.isActive)

    def testDefinitionRejectsBadInput(self) -> None:
        with self.assertRaises(ValidationFailedError):
            AIVectorSpaceDefinition(tenantId=TENANT, space="DEFAULT_SPACE")  # type: ignore[arg-type]
        with self.assertRaises(ValidationFailedError):
            AIVectorSpaceDefinition(tenantId=TENANT, space=space(), metadata=["nope"])  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            AIVectorSpaceDefinition(tenantId="not-a-uuid", space=space())  # type: ignore[arg-type]


class StoredEmbeddingTests(unittest.TestCase):
    def build(self, **overrides: object) -> AIStoredEmbedding:
        params: dict = {
            "tenantId": TENANT,
            "space": space(),
            "sourceType": "KNOWLEDGE_CHUNK",
            "sourceId": "chunk-1",
            "vector": normalizeVector([1.0, 0.0, 0.0, 0.0]),
            "contentHash": contentFingerprint("hello", space()),
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIStoredEmbedding(**params)

    def testValidRowExposesDimensionsAndTenantCheck(self) -> None:
        embedding = self.build()
        self.assertEqual(embedding.dimensions, 4)
        self.assertTrue(embedding.belongsTo(TENANT))
        self.assertFalse(embedding.belongsTo(OTHER_TENANT))
        self.assertTrue(embedding.sameSpaceAs(space()))
        self.assertFalse(embedding.sameSpaceAs(space(dimensions=8)))

    def testNormalizedSpaceRejectsNonUnitVector(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.build(vector=(3.0, 4.0, 0.0, 0.0))

    def testUnnormalizedSpaceAcceptsRawVector(self) -> None:
        embedding = self.build(space=space(normalization="NONE"), vector=(3.0, 4.0, 0.0, 0.0))
        self.assertEqual(embedding.vector, (3.0, 4.0, 0.0, 0.0))

    def testDimensionalityMustMatchTheSpace(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.build(vector=normalizeVector([1.0, 0.0]))

    def testFingerprintAndSourceGuards(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.build(contentHash="not-a-digest")
        with self.assertRaises(ValidationFailedError):
            self.build(sourceId="   ")
        with self.assertRaises(ValidationFailedError):
            self.build(sourceId="x" * (MAX_SOURCE_ID_LENGTH + 1))
        with self.assertRaises(ValidationFailedError):
            self.build(tokenCount=-1)

    def testHelpersNormalizeTheirInput(self) -> None:
        digest = contentFingerprint("hello", space())
        self.assertEqual(ensureFingerprint(digest.upper()), digest)
        self.assertEqual(ensureSourceId("  chunk-9 "), "chunk-9")

    def testMatchesContentRecomputesTheFingerprint(self) -> None:
        embedding = self.build()
        self.assertTrue(embedding.matchesContent("hello"))
        self.assertTrue(embedding.matchesContent("  hello  "))
        self.assertFalse(embedding.matchesContent("goodbye"))

    def testScoreComparesAgainstAQueryVector(self) -> None:
        embedding = self.build()
        self.assertAlmostEqual(embedding.score(normalizeVector([1.0, 0.0, 0.0, 0.0])), 1.0)
        self.assertAlmostEqual(embedding.score(normalizeVector([0.0, 1.0, 0.0, 0.0])), 0.0)

    def testBridgeToPhase13BEmbedding(self) -> None:
        modelId = uuid.uuid4()
        bridged = self.build(modelId=modelId).toDomainEmbedding()
        self.assertIsInstance(bridged, AIEmbedding)
        self.assertEqual(bridged.modelId, modelId)
        self.assertEqual(bridged.dimensions, 4)

    def testBridgeRefusesWhenModelIsUnknown(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.build().toDomainEmbedding()


class EmbeddingItemTests(unittest.TestCase):
    def testItemCanonicalizesTextAndDefaultsSource(self) -> None:
        item = EmbeddingItem(text="  Hello   world  ")
        self.assertEqual(item.text, "Hello world")
        self.assertEqual(item.sourceType, "CUSTOM")
        self.assertTrue(item.sourceId)

    def testEmptyTextIsRejected(self) -> None:
        with self.assertRaises(AIEmbeddingInvalid):
            EmbeddingItem(text="   ")

    def testMetadataMustBeAMapping(self) -> None:
        with self.assertRaises(AIEmbeddingInvalid):
            EmbeddingItem(text="hi", metadata=["nope"])  # type: ignore[arg-type]

    def testTokenEstimateIsMonotonic(self) -> None:
        short = EmbeddingItem(text="a" * 8, sourceId="s")
        long = EmbeddingItem(text="a" * 400, sourceId="s")
        self.assertGreater(long.estimatedTokens, short.estimatedTokens)

    def testItemIsFrozen(self) -> None:
        item = EmbeddingItem(text="hi", sourceId="s")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            item.text = "other"  # type: ignore[misc]


class EmbeddingEnginePlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EmbeddingEngine(maxBatchSize=2, maxInputTokens=64, now=frozenClock)
        self.space = space()

    def items(self, *texts: str) -> tuple[EmbeddingItem, ...]:
        return tuple(
            EmbeddingItem(text=text, sourceType="KNOWLEDGE_CHUNK", sourceId=f"chunk-{index}")
            for index, text in enumerate(texts)
        )

    def testEngineRejectsInvalidConfiguration(self) -> None:
        with self.assertRaises(AIEmbeddingInvalid):
            EmbeddingEngine(maxBatchSize=0)
        with self.assertRaises(AIEmbeddingInvalid):
            EmbeddingEngine(maxBatchSize=MAX_BATCH_SIZE + 1)
        with self.assertRaises(AIEmbeddingInvalid):
            EmbeddingEngine(maxInputTokens=0)

    def testPlanKeepsOrderAndSplitsIntoBatches(self) -> None:
        plan = self.engine.plan(self.space, self.items("alpha", "beta", "gamma"))
        self.assertEqual(len(plan.pending), 3)
        self.assertEqual(plan.providerCalls, 2)
        self.assertEqual([item.text for item in plan.batches[0]], ["alpha", "beta"])
        self.assertEqual([item.text for item in plan.batches[1]], ["gamma"])
        self.assertFalse(plan.isEmpty)

    def testIdenticalTextsAreDeduplicatedByFingerprint(self) -> None:
        plan = self.engine.plan(self.space, self.items("alpha", "  alpha ", "beta"))
        self.assertEqual(len(plan.pending), 2)
        self.assertEqual(plan.duplicates, 1)

    def testKnownFingerprintsAreSubtractedFromTheWork(self) -> None:
        items = self.items("alpha", "beta")
        known = (items[0].fingerprint(self.space),)
        plan = self.engine.plan(self.space, items, knownFingerprints=known)
        self.assertEqual(len(plan.pending), 1)
        self.assertEqual(len(plan.cached), 1)
        self.assertEqual(plan.cached[0].text, "alpha")

    def testFullyCachedPlanRequestsNoProviderCall(self) -> None:
        items = self.items("alpha")
        plan = self.engine.plan(
            self.space, items, knownFingerprints=(items[0].fingerprint(self.space),)
        )
        self.assertTrue(plan.isEmpty)
        self.assertEqual(plan.providerCalls, 0)
        self.assertEqual(plan.estimatedTokens, 0)

    def testOversizedTextIsRejectedNotTruncated(self) -> None:
        with self.assertRaises(AITokenLimitExceeded):
            self.engine.plan(self.space, self.items("x" * 5000))

    def testAbsolutePlatformCeilingIsEnforced(self) -> None:
        crowd = tuple(
            EmbeddingItem(text=f"text-{index}", sourceId=f"s-{index}")
            for index in range(MAX_BATCH_SIZE + 1)
        )
        with self.assertRaises(AIEmbeddingBatchTooLarge):
            self.engine.plan(self.space, crowd)

    def testConfiguredCeilingIsEnforcedWhenRequested(self) -> None:
        with self.assertRaises(AIEmbeddingBatchTooLarge):
            self.engine.plan(self.space, self.items("a", "b", "c"), maxItems=2)
        with self.assertRaises(AIEmbeddingBatchTooLarge):
            self.engine.plan(self.space, self.items("a"), maxItems=0)

    def testPlanRejectsForeignTypes(self) -> None:
        with self.assertRaises(AIEmbeddingInvalid):
            self.engine.plan(self.space, ["raw string"])  # type: ignore[list-item]
        with self.assertRaises(AIEmbeddingInvalid):
            self.engine.plan("SPACE", self.items("a"))  # type: ignore[arg-type]

    def testPlanFingerprintsMatchItsPendingItems(self) -> None:
        plan = self.engine.plan(self.space, self.items("alpha", "beta"))
        self.assertEqual(
            plan.fingerprints(),
            tuple(item.fingerprint(self.space) for item in plan.pending),
        )


class EmbeddingEngineConstructionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EmbeddingEngine(maxBatchSize=4, maxInputTokens=1024, now=frozenClock)
        self.space = space()
        self.item = EmbeddingItem(text="alpha", sourceType="DOCUMENT", sourceId="doc-1")

    def testBuiltEmbeddingIsNormalizedStampedAndFingerprinted(self) -> None:
        embedding = self.engine.buildEmbedding(
            TENANT, self.space, self.item, [3.0, 4.0, 0.0, 0.0], providerCode="local"
        )
        self.assertTrue(isUnitVector(embedding.vector))
        self.assertEqual(embedding.createdAt, CLOCK)
        self.assertEqual(embedding.providerCode, "LOCAL")
        self.assertEqual(embedding.contentHash, self.item.fingerprint(self.space))
        self.assertEqual(embedding.tokenCount, self.item.estimatedTokens)

    def testBuiltEmbeddingRejectsProviderNoise(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.engine.buildEmbedding(TENANT, self.space, self.item, [1.0, 2.0])
        with self.assertRaises(ValidationFailedError):
            self.engine.buildEmbedding(TENANT, self.space, self.item, [1.0, float("nan"), 0.0, 0.0])
        with self.assertRaises(ValidationFailedError):
            self.engine.buildEmbedding(TENANT, self.space, self.item, [0.0, 0.0, 0.0, 0.0])

    def testExplicitTokenCountWins(self) -> None:
        embedding = self.engine.buildEmbedding(
            TENANT, self.space, self.item, [1.0, 0.0, 0.0, 0.0], tokenCount=42
        )
        self.assertEqual(embedding.tokenCount, 42)

    def testBatchIsZippedOntoItsItems(self) -> None:
        items = (
            EmbeddingItem(text="alpha", sourceId="a"),
            EmbeddingItem(text="beta", sourceId="b"),
        )
        built = self.engine.buildBatch(
            TENANT, self.space, items, [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
        )
        self.assertEqual([row.sourceId for row in built], ["a", "b"])
        self.assertEqual({row.createdAt for row in built}, {CLOCK})

    def testMisalignedProviderResponseIsRefusedWholesale(self) -> None:
        items = (EmbeddingItem(text="alpha", sourceId="a"),)
        with self.assertRaises(AIEmbeddingInvalid):
            self.engine.buildBatch(
                TENANT, self.space, items, [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]
            )
        with self.assertRaises(AIEmbeddingInvalid):
            self.engine.buildBatch(
                TENANT, self.space, items, [[1.0, 0.0, 0.0, 0.0]], tokenCounts=[1, 2]
            )

    def testPrepareQueryBuildsATransientQueryItem(self) -> None:
        item = self.engine.prepareQuery(self.space, "  what is the KPI?  ")
        self.assertEqual(item.sourceType, "QUERY")
        self.assertEqual(item.text, "what is the KPI?")

    def testPrepareQueryHonoursTheTokenBudget(self) -> None:
        engine = EmbeddingEngine(maxBatchSize=2, maxInputTokens=4, now=frozenClock)
        with self.assertRaises(AITokenLimitExceeded):
            engine.prepareQuery(self.space, "x" * 500)


class RankingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.space = space()
        self.engine = EmbeddingEngine(maxBatchSize=4, maxInputTokens=1024, now=frozenClock)

    def stored(self, sourceId: str, vector: list[float], **overrides: object) -> AIStoredEmbedding:
        params: dict = {
            "tenantId": TENANT,
            "space": self.space,
            "sourceType": "KNOWLEDGE_CHUNK",
            "sourceId": sourceId,
            "vector": normalizeVector(vector),
            "contentHash": contentFingerprint(sourceId, self.space),
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIStoredEmbedding(**params)

    def testMostSimilarCandidateRanksFirst(self) -> None:
        candidates = [
            self.stored("far", [0.0, 1.0, 0.0, 0.0]),
            self.stored("near", [1.0, 0.1, 0.0, 0.0]),
            self.stored("exact", [1.0, 0.0, 0.0, 0.0]),
        ]
        matches = rankBySimilarity(self.space, [1.0, 0.0, 0.0, 0.0], candidates, topK=3)
        self.assertEqual([match.sourceId for match in matches], ["exact", "near", "far"])
        self.assertAlmostEqual(matches[0].score, 1.0)

    def testTopKTruncatesAfterRanking(self) -> None:
        candidates = [
            self.stored("a", [1.0, 0.0, 0.0, 0.0]),
            self.stored("b", [0.9, 0.1, 0.0, 0.0]),
            self.stored("c", [0.0, 1.0, 0.0, 0.0]),
        ]
        matches = rankBySimilarity(self.space, [1.0, 0.0, 0.0, 0.0], candidates, topK=2)
        self.assertEqual(len(matches), 2)
        self.assertEqual([match.sourceId for match in matches], ["a", "b"])

    def testMinScoreFiltersWeakMatches(self) -> None:
        candidates = [
            self.stored("strong", [1.0, 0.0, 0.0, 0.0]),
            self.stored("weak", [0.0, 1.0, 0.0, 0.0]),
        ]
        matches = rankBySimilarity(
            self.space, [1.0, 0.0, 0.0, 0.0], candidates, topK=5, minScore=0.5
        )
        self.assertEqual([match.sourceId for match in matches], ["strong"])

    def testEqualScoresBreakDeterministicallyBySourceId(self) -> None:
        candidates = [
            self.stored("zulu", [1.0, 0.0, 0.0, 0.0]),
            self.stored("alpha", [1.0, 0.0, 0.0, 0.0]),
            self.stored("mike", [1.0, 0.0, 0.0, 0.0]),
        ]
        first = rankBySimilarity(self.space, [1.0, 0.0, 0.0, 0.0], candidates, topK=3)
        second = rankBySimilarity(
            self.space, [1.0, 0.0, 0.0, 0.0], list(reversed(candidates)), topK=3
        )
        self.assertEqual([match.sourceId for match in first], ["alpha", "mike", "zulu"])
        self.assertEqual([m.sourceId for m in first], [m.sourceId for m in second])

    def testCandidateFromAnotherSpaceIsAHardError(self) -> None:
        foreign = AIStoredEmbedding(
            tenantId=TENANT,
            space=space(code="OTHER_SPACE"),
            sourceType="DOCUMENT",
            sourceId="doc",
            vector=normalizeVector([1.0, 0.0, 0.0, 0.0]),
            contentHash=contentFingerprint("doc", space(code="OTHER_SPACE")),
        )
        with self.assertRaises(AIVectorSpaceMismatch):
            rankBySimilarity(self.space, [1.0, 0.0, 0.0, 0.0], [foreign], topK=1)

    def testRankingRejectsNonPositiveTopK(self) -> None:
        with self.assertRaises(AIEmbeddingInvalid):
            rankBySimilarity(self.space, [1.0, 0.0, 0.0, 0.0], [], topK=0)

    def testEmptyCandidateSetProducesNoMatches(self) -> None:
        self.assertEqual(rankBySimilarity(self.space, [1.0, 0.0, 0.0, 0.0], [], topK=5), ())

    def testMatchesCarryNoContent(self) -> None:
        match = SimilarityMatch.fromEmbedding(self.stored("a", [1.0, 0.0, 0.0, 0.0]), 0.5)
        self.assertFalse(hasattr(match, "vector"))
        self.assertFalse(hasattr(match, "text"))
        self.assertEqual(match.score, 0.5)
        self.assertEqual(len(match.contentHash), 64)

    def testRankingWorksInAnUnnormalizedEuclideanSpace(self) -> None:
        metricSpace = space(code="EUCLID_SPACE", metric="EUCLIDEAN", normalization="NONE")
        near = AIStoredEmbedding(
            tenantId=TENANT,
            space=metricSpace,
            sourceType="DOCUMENT",
            sourceId="near",
            vector=(0.0, 0.0, 0.0, 1.0),
            contentHash=contentFingerprint("near", metricSpace),
        )
        far = AIStoredEmbedding(
            tenantId=TENANT,
            space=metricSpace,
            sourceType="DOCUMENT",
            sourceId="far",
            vector=(0.0, 0.0, 0.0, 9.0),
            contentHash=contentFingerprint("far", metricSpace),
        )
        matches = rankBySimilarity(metricSpace, [0.0, 0.0, 0.0, 0.0], [far, near], topK=2)
        self.assertEqual([match.sourceId for match in matches], ["near", "far"])

    def testScoresNeverExceedTheCosineRange(self) -> None:
        candidates = [self.stored("a", [1.0, 0.0, 0.0, 0.0])]
        match = rankBySimilarity(self.space, [1.0, 0.0, 0.0, 0.0], candidates, topK=1)[0]
        self.assertTrue(math.isfinite(match.score))
        self.assertLessEqual(match.score, 1.0)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
