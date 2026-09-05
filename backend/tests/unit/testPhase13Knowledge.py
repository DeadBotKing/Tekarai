"""Phase 13-R unit tests — knowledge chunking and index planning, offline.

Covers the closed vocabularies, content canonicalization and checksums,
``ChunkingPolicy`` validation, all three split strategies (paragraph,
sentence, fixed-token) with their budget, overlap, offset and short-tail
rules, determinism and idempotency of the split, the two entities with
their lifecycle machines and guards, and the incremental ``IndexPlanner``
(create, unchanged, checksum reuse across moved positions, additions,
removals, forced reindex, policy change).

No Django, database, network, provider, or clock dependency.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime

from apps.ai.domain.entities.aiRecords import AIKnowledgeChunk
from apps.ai.domain.entities.knowledgeRecords import (
    MAX_ENTITY_ID_LENGTH,
    AIKnowledgeChunkRecord,
    AIKnowledgeSourceRecord,
    ensureChecksum,
    ensureEntityId,
    ensureEntityKind,
)
from apps.ai.domain.exceptions import AIKnowledgeChunkInvalid, AIKnowledgeSourceInvalid
from apps.ai.domain.services.knowledgeChunker import (
    ChunkingService,
    IndexPlanner,
    buildChunkRecords,
)
from apps.ai.domain.valueObjects.knowledgeTypes import (
    CHUNK_STRATEGIES,
    INDEX_ACTIONS,
    KNOWLEDGE_SOURCE_DOMAINS,
    MAX_CHUNK_TOKENS,
    ChunkingPolicy,
    canonicalContent,
    chunkChecksum,
    contentChecksum,
    ensureChunkStrategy,
    ensureIndexAction,
    ensureSourceDomain,
    splitParagraphs,
    splitSentences,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("33333333-3333-4333-8333-333333333333")
SOURCE = uuid.UUID("44444444-4444-4444-8444-444444444444")

PARAGRAPHS = (
    "The quarterly production report covers three pharmaceutical lines.\n\n"
    "Line one reached ninety two percent of its planned output.\n\n"
    "Line two was halted twice for preventive maintenance.\n\n"
    "Line three exceeded its target by four percent."
)


def words(count: int, token: str = "word") -> str:
    return " ".join(f"{token}{index}" for index in range(count))


class VocabularyTests(unittest.TestCase):
    def testClosedVocabulariesAreStable(self) -> None:
        self.assertIn("DOCUMENTS", KNOWLEDGE_SOURCE_DOMAINS)
        self.assertIn("MEETINGS", KNOWLEDGE_SOURCE_DOMAINS)
        self.assertEqual(CHUNK_STRATEGIES, ("FIXED_TOKEN", "PARAGRAPH", "SENTENCE"))
        self.assertEqual(INDEX_ACTIONS, ("CREATE", "REINDEX", "UNCHANGED", "ARCHIVE"))

    def testVocabularyValuesAreNormalized(self) -> None:
        self.assertEqual(ensureSourceDomain(" documents "), "DOCUMENTS")
        self.assertEqual(ensureChunkStrategy("sentence"), "SENTENCE")
        self.assertEqual(ensureIndexAction("reindex"), "REINDEX")
        with self.assertRaises(ValidationFailedError):
            ensureSourceDomain("INVOICES")
        with self.assertRaises(ValidationFailedError):
            ensureChunkStrategy("SEMANTIC")


class CanonicalContentTests(unittest.TestCase):
    def testCosmeticNoiseDoesNotChangeTheChecksum(self) -> None:
        first = contentChecksum("Hello   world\r\n\r\n\r\nSecond   paragraph  ")
        second = contentChecksum("Hello world\n\nSecond paragraph")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    def testParagraphStructureSurvivesCanonicalization(self) -> None:
        canonical = canonicalContent("a\n\n\n\nb")
        self.assertEqual(canonical, "a\n\nb")

    def testRealChangesProduceANewChecksum(self) -> None:
        self.assertNotEqual(contentChecksum("alpha"), contentChecksum("alpha beta"))

    def testEmptyContentIsRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            contentChecksum("   \n  ")
        with self.assertRaises(ValidationFailedError):
            canonicalContent(None)  # type: ignore[arg-type]

    def testChunkChecksumIsWhitespaceInsensitive(self) -> None:
        self.assertEqual(chunkChecksum("a  b"), chunkChecksum(" a b "))
        with self.assertRaises(ValidationFailedError):
            chunkChecksum("  ")

    def testSplitHelpersRespectStructure(self) -> None:
        self.assertEqual(len(splitParagraphs(canonicalContent(PARAGRAPHS))), 4)
        sentences = splitSentences("First one. Second one! Third one؟")
        self.assertEqual(len(sentences), 3)
        self.assertTrue(sentences[0].endswith("."))


class ChunkingPolicyTests(unittest.TestCase):
    def testDefaultsAreValid(self) -> None:
        policy = ChunkingPolicy()
        self.assertEqual(policy.strategy, "PARAGRAPH")
        self.assertEqual(policy.signature(), "PARAGRAPH|512|64|32")

    def testOverlapMustBeSmallerThanBudget(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ChunkingPolicy(maxTokens=100, overlapTokens=100)
        with self.assertRaises(ValidationFailedError):
            ChunkingPolicy(maxTokens=100, overlapTokens=-1)

    def testBudgetIsBounded(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ChunkingPolicy(maxTokens=0)
        with self.assertRaises(ValidationFailedError):
            ChunkingPolicy(maxTokens=MAX_CHUNK_TOKENS + 1)

    def testMinimumMustNotExceedBudget(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ChunkingPolicy(maxTokens=50, minTokens=51)

    def testNonIntegerValuesAreRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ChunkingPolicy(maxTokens=True)


class ChunkingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = ChunkingService()

    def testParagraphStrategyKeepsWholeParagraphsTogether(self) -> None:
        result = self.service.split(
            PARAGRAPHS,
            policy=ChunkingPolicy(strategy="PARAGRAPH", maxTokens=20, overlapTokens=0, minTokens=0),
        )
        self.assertGreaterEqual(len(result.chunks), 3)
        self.assertTrue(result.chunks[0].text.startswith("The quarterly production report"))
        for chunk in result.chunks:
            self.assertLessEqual(chunk.tokenCount, 20)

    def testOrdinalsAreSequentialFromZero(self) -> None:
        result = self.service.split(
            PARAGRAPHS, policy=ChunkingPolicy(maxTokens=15, overlapTokens=0, minTokens=0)
        )
        self.assertEqual(
            [chunk.ordinal for chunk in result.chunks], list(range(len(result.chunks)))
        )

    def testSplitIsDeterministicAndIdempotent(self) -> None:
        policy = ChunkingPolicy(maxTokens=18, overlapTokens=4, minTokens=0)
        first = self.service.split(PARAGRAPHS, policy=policy)
        second = self.service.split(PARAGRAPHS, policy=policy)
        self.assertEqual(first.checksums, second.checksums)
        self.assertEqual(first.checksum, second.checksum)

    def testCosmeticWhitespaceDoesNotChangeChunkChecksums(self) -> None:
        policy = ChunkingPolicy(maxTokens=18, overlapTokens=0, minTokens=0)
        noisy = PARAGRAPHS.replace("\n\n", "\n\n\n").replace(" ", "  ")
        self.assertEqual(
            self.service.split(PARAGRAPHS, policy=policy).checksums,
            self.service.split(noisy, policy=policy).checksums,
        )

    def testFixedTokenStrategyRespectsTheBudget(self) -> None:
        result = self.service.split(
            words(400),
            policy=ChunkingPolicy(
                strategy="FIXED_TOKEN", maxTokens=30, overlapTokens=0, minTokens=0
            ),
        )
        self.assertGreater(len(result.chunks), 5)
        for chunk in result.chunks:
            self.assertLessEqual(chunk.tokenCount, 30)

    def testFixedTokenOverlapRepeatsTheTail(self) -> None:
        result = self.service.split(
            words(120),
            policy=ChunkingPolicy(
                strategy="FIXED_TOKEN", maxTokens=20, overlapTokens=8, minTokens=0
            ),
        )
        self.assertGreater(len(result.chunks), 2)
        firstTail = result.chunks[0].text.split()[-1]
        self.assertIn(firstTail, result.chunks[1].text.split())

    def testZeroOverlapProducesDisjointChunks(self) -> None:
        result = self.service.split(
            words(90),
            policy=ChunkingPolicy(
                strategy="FIXED_TOKEN", maxTokens=20, overlapTokens=0, minTokens=0
            ),
        )
        rebuilt = " ".join(chunk.text for chunk in result.chunks)
        self.assertEqual(rebuilt.split(), result.canonical.split())

    def testSentenceStrategyPacksWholeSentences(self) -> None:
        text = "Alpha one. Beta two. Gamma three. Delta four."
        result = self.service.split(
            text,
            policy=ChunkingPolicy(strategy="SENTENCE", maxTokens=6, overlapTokens=0, minTokens=0),
        )
        self.assertGreaterEqual(len(result.chunks), 2)
        self.assertTrue(result.chunks[0].text.startswith("Alpha one."))

    def testOversizedParagraphIsSplitInsteadOfOverflowing(self) -> None:
        text = f"{words(200)}\n\nshort tail paragraph"
        result = self.service.split(
            text,
            policy=ChunkingPolicy(strategy="PARAGRAPH", maxTokens=25, overlapTokens=0, minTokens=0),
        )
        for chunk in result.chunks:
            self.assertLessEqual(chunk.tokenCount, 25)

    def testOffsetsPointBackIntoTheCanonicalText(self) -> None:
        result = self.service.split(
            PARAGRAPHS, policy=ChunkingPolicy(maxTokens=20, overlapTokens=0, minTokens=0)
        )
        for chunk in result.chunks:
            self.assertLessEqual(chunk.endOffset, len(result.canonical))
            self.assertLess(chunk.startOffset, chunk.endOffset)
            excerpt = result.canonical[chunk.startOffset : chunk.endOffset]
            self.assertEqual(excerpt.split()[0], chunk.text.split()[0])

    def testShortTailIsRebalancedAgainstItsPredecessor(self) -> None:
        # A 13-word paragraph (20 tokens) plus a one-token tail cannot be
        # packed together under a 20-token budget, so the split leaves an
        # orphan; minTokens=10 pulls words back until both sides clear it.
        document = f"{words(13)}\n\ntiny"
        loose = ChunkingPolicy(maxTokens=20, overlapTokens=0, minTokens=0)
        strict = ChunkingPolicy(maxTokens=20, overlapTokens=0, minTokens=10)
        orphaned = self.service.split(document, policy=loose)
        balanced = self.service.split(document, policy=strict)
        self.assertEqual(len(orphaned.chunks), 2)
        self.assertLess(orphaned.chunks[-1].tokenCount, 10)
        self.assertEqual(len(balanced.chunks), 2)
        for chunk in balanced.chunks:
            self.assertGreaterEqual(chunk.tokenCount, 10)
            self.assertLessEqual(chunk.tokenCount, 20)
        self.assertTrue(balanced.chunks[-1].text.endswith("tiny"))

    def testRebalancingNeverDropsOrDuplicatesText(self) -> None:
        document = f"{words(13)}\n\ntiny"
        balanced = self.service.split(
            document, policy=ChunkingPolicy(maxTokens=20, overlapTokens=0, minTokens=10)
        )
        rebuilt = " ".join(chunk.text for chunk in balanced.chunks)
        self.assertEqual(rebuilt.split(), balanced.canonical.split())

    def testRebalancingIsSkippedWhenThePredecessorCannotAfford(self) -> None:
        # A four-word paragraph (~6 tokens) and a one-character tail under a
        # 6-token budget: moving enough words would starve the predecessor,
        # so the orphan is kept rather than mangling the split.
        document = f"{words(4)}\n\nx"
        result = self.service.split(
            document, policy=ChunkingPolicy(maxTokens=6, overlapTokens=0, minTokens=5)
        )
        self.assertEqual(len(result.chunks), 2)
        self.assertEqual(result.chunks[-1].text, "x")

    def testTotalsAreReported(self) -> None:
        result = self.service.split(
            PARAGRAPHS, policy=ChunkingPolicy(maxTokens=20, overlapTokens=0, minTokens=0)
        )
        self.assertEqual(result.tokenCount, sum(chunk.tokenCount for chunk in result.chunks))
        self.assertEqual(len(result.checksums), len(result.chunks))

    def testEmptyContentAndBadPolicyAreRejected(self) -> None:
        with self.assertRaises(AIKnowledgeChunkInvalid):
            self.service.split("    ")
        with self.assertRaises(AIKnowledgeChunkInvalid):
            self.service.split("text", policy="PARAGRAPH")  # type: ignore[arg-type]

    def testSingleShortDocumentProducesOneChunk(self) -> None:
        result = self.service.split("A single short sentence about safety.")
        self.assertEqual(len(result.chunks), 1)
        self.assertEqual(result.chunks[0].ordinal, 0)


class KnowledgeSourceRecordTests(unittest.TestCase):
    def build(self, **overrides: object) -> AIKnowledgeSourceRecord:
        params: dict = {
            "tenantId": TENANT,
            "sourceDomain": "DOCUMENTS",
            "sourceEntityType": "document",
            "sourceEntityId": "doc-1",
            "title": "Quarterly report",
            "checksum": contentChecksum("body"),
            "createdAt": CLOCK,
            "updatedAt": CLOCK,
        }
        params.update(overrides)
        return AIKnowledgeSourceRecord(**params)

    def testNormalizationAndNaturalKey(self) -> None:
        source = self.build()
        self.assertEqual(source.sourceEntityType, "DOCUMENT")
        self.assertEqual(source.naturalKey, ("DOCUMENTS", "DOCUMENT", "doc-1"))
        self.assertEqual(source.reference(), "DOCUMENTS:DOCUMENT:doc-1")
        self.assertEqual(source.status, "PENDING")
        self.assertEqual(source.revision, 0)

    def testGuardsRejectBadInput(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.build(title="   ")
        with self.assertRaises(ValidationFailedError):
            self.build(checksum="nope")
        with self.assertRaises(ValidationFailedError):
            self.build(sourceEntityId="x" * (MAX_ENTITY_ID_LENGTH + 1))
        with self.assertRaises(ValidationFailedError):
            self.build(revision=-1)
        with self.assertRaises(ValidationFailedError):
            self.build(metadata=["nope"])

    def testLifecycleFollowsTheSharedStateMachine(self) -> None:
        source = self.build()
        source.transitionTo("INDEXING", now=CLOCK)
        source.transitionTo("READY", now=CLOCK)
        source.transitionTo("ARCHIVED", now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            source.transitionTo("INDEXING", now=CLOCK)

    def testIllegalTransitionIsRejected(self) -> None:
        source = self.build()
        with self.assertRaises(ValidationFailedError):
            source.transitionTo("READY", now=CLOCK)

    def testMarkIndexedBumpsRevisionAndClearsError(self) -> None:
        source = self.build(status="FAILED", errorCode="AI_KNOWLEDGE_INGESTION_FAILED")
        source.transitionTo("INDEXING", now=CLOCK)
        policy = ChunkingPolicy()
        source.markIndexed(
            checksum=contentChecksum("new body"),
            chunkCount=3,
            tokenCount=90,
            policy=policy,
            spaceCode="kpi_space",
            now=CLOCK,
        )
        self.assertEqual(source.status, "READY")
        self.assertEqual(source.revision, 1)
        self.assertEqual(source.chunkCount, 3)
        self.assertEqual(source.spaceCode, "KPI_SPACE")
        self.assertEqual(source.policySignature, policy.signature())
        self.assertEqual(source.errorCode, "")
        self.assertEqual(source.lastIndexedAt, CLOCK)

    def testMarkFailedRecordsAStableCode(self) -> None:
        source = self.build()
        source.transitionTo("INDEXING", now=CLOCK)
        source.markFailed("ai_provider_unavailable", now=CLOCK)
        self.assertEqual(source.status, "FAILED")
        self.assertEqual(source.errorCode, "AI_PROVIDER_UNAVAILABLE")

    def testArchiveClearsCountersAndBlocksIngestion(self) -> None:
        source = self.build(status="READY", chunkCount=5, tokenCount=100)
        source.archive(now=CLOCK)
        self.assertEqual(source.status, "ARCHIVED")
        self.assertEqual(source.chunkCount, 0)
        with self.assertRaises(ValidationFailedError):
            source.requireIngestable()

    def testChangeDetectionHelpers(self) -> None:
        source = self.build()
        self.assertFalse(source.hasContentChanged(contentChecksum("body")))
        self.assertTrue(source.hasContentChanged(contentChecksum("other")))
        self.assertFalse(source.matchesPolicy(ChunkingPolicy()))
        source.policySignature = ChunkingPolicy().signature()
        self.assertTrue(source.matchesPolicy(ChunkingPolicy()))

    def testHelperNormalizers(self) -> None:
        digest = contentChecksum("body")
        self.assertEqual(ensureChecksum(digest.upper()), digest)
        self.assertEqual(ensureEntityId("  doc-2 "), "doc-2")
        self.assertEqual(ensureEntityKind(" document "), "DOCUMENT")
        with self.assertRaises(ValidationFailedError):
            ensureEntityKind("")


class KnowledgeChunkRecordTests(unittest.TestCase):
    def build(self, **overrides: object) -> AIKnowledgeChunkRecord:
        params: dict = {
            "tenantId": TENANT,
            "sourceId": SOURCE,
            "ordinal": 0,
            "text": "Line one reached ninety two percent.",
            "checksum": chunkChecksum("Line one reached ninety two percent."),
            "tokenCount": 9,
            "startOffset": 0,
            "endOffset": 36,
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIKnowledgeChunkRecord(**params)

    def testValidChunkExposesItsEmbeddingReference(self) -> None:
        chunk = self.build()
        self.assertEqual(chunk.embeddingSourceId, str(chunk.id))
        self.assertEqual(chunk.classification, "INTERNAL")

    def testGuardsRejectBadInput(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.build(text="   ")
        with self.assertRaises(ValidationFailedError):
            self.build(checksum="short")
        with self.assertRaises(ValidationFailedError):
            self.build(ordinal=-1)
        with self.assertRaises(ValidationFailedError):
            self.build(startOffset=50, endOffset=10)
        with self.assertRaises(ValidationFailedError):
            self.build(classification="SECRET")

    def testReorderMovesAReusedChunk(self) -> None:
        chunk = self.build()
        chunk.reorder(7)
        self.assertEqual(chunk.ordinal, 7)
        with self.assertRaises(ValidationFailedError):
            chunk.reorder(-2)

    def testBridgeToPhase13BChunk(self) -> None:
        bridged = self.build().toDomainChunk()
        self.assertIsInstance(bridged, AIKnowledgeChunk)
        self.assertEqual(bridged.itemId, SOURCE)
        self.assertEqual(bridged.tokenCount, 9)


class IndexPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.chunker = ChunkingService()
        self.planner = IndexPlanner()
        self.policy = ChunkingPolicy(maxTokens=20, overlapTokens=0, minTokens=0)

    def source(self, result, **overrides: object) -> AIKnowledgeSourceRecord:
        params: dict = {
            "tenantId": TENANT,
            "sourceDomain": "DOCUMENTS",
            "sourceEntityType": "DOCUMENT",
            "sourceEntityId": "doc-1",
            "title": "Report",
            "checksum": result.checksum,
            "status": "READY",
            "policySignature": self.policy.signature(),
            "chunkCount": len(result.chunks),
            "tokenCount": result.tokenCount,
            "id": SOURCE,
        }
        params.update(overrides)
        return AIKnowledgeSourceRecord(**params)

    def records(self, result) -> tuple[AIKnowledgeChunkRecord, ...]:
        return buildChunkRecords(TENANT, SOURCE, result.chunks)

    def testFirstIngestionIsACreate(self) -> None:
        result = self.chunker.split(PARAGRAPHS, policy=self.policy)
        plan = self.planner.plan(None, result)
        self.assertEqual(plan.action, "CREATE")
        self.assertEqual(plan.addedCount, len(result.chunks))
        self.assertEqual(plan.reusedCount, 0)
        self.assertFalse(plan.isNoop)

    def testIdenticalContentIsANoop(self) -> None:
        result = self.chunker.split(PARAGRAPHS, policy=self.policy)
        plan = self.planner.plan(self.source(result), result, self.records(result))
        self.assertTrue(plan.isNoop)
        self.assertEqual(plan.addedCount, 0)
        self.assertEqual(plan.removedCount, 0)

    def testForceOverridesTheNoop(self) -> None:
        result = self.chunker.split(PARAGRAPHS, policy=self.policy)
        plan = self.planner.plan(self.source(result), result, self.records(result), force=True)
        self.assertEqual(plan.action, "REINDEX")
        self.assertEqual(plan.addedCount, 0)
        self.assertEqual(plan.reusedCount, len(result.chunks))
        self.assertEqual(plan.reason, "Reindex forced by the caller.")

    def testUnchangedParagraphsAreReusedWhenOneIsAppended(self) -> None:
        original = self.chunker.split(PARAGRAPHS, policy=self.policy)
        stored = self.records(original)
        updated = self.chunker.split(
            f"{PARAGRAPHS}\n\nLine four is a brand new paragraph.", policy=self.policy
        )
        plan = self.planner.plan(self.source(original), updated, stored)
        self.assertEqual(plan.action, "REINDEX")
        self.assertEqual(plan.reusedCount, len(original.chunks))
        self.assertEqual(plan.addedCount, len(updated.chunks) - len(original.chunks))
        self.assertEqual(plan.removedCount, 0)

    def testReuseSurvivesAParagraphInsertedAtTheTop(self) -> None:
        original = self.chunker.split(PARAGRAPHS, policy=self.policy)
        stored = self.records(original)
        updated = self.chunker.split(
            f"A brand new opening paragraph.\n\n{PARAGRAPHS}", policy=self.policy
        )
        plan = self.planner.plan(self.source(original), updated, stored)
        self.assertEqual(plan.reusedCount, len(original.chunks))
        self.assertEqual(plan.addedCount, 1)
        # every reused chunk is assigned its shifted position
        self.assertEqual(
            sorted(ordinal for _, ordinal in plan.reused), list(range(1, len(original.chunks) + 1))
        )

    def testRemovedParagraphIsReportedForDeletion(self) -> None:
        original = self.chunker.split(PARAGRAPHS, policy=self.policy)
        stored = self.records(original)
        shorter = "\n\n".join(PARAGRAPHS.split("\n\n")[:2])
        updated = self.chunker.split(shorter, policy=self.policy)
        plan = self.planner.plan(self.source(original), updated, stored)
        self.assertGreater(plan.removedCount, 0)
        self.assertEqual(plan.addedCount, 0)

    def testPolicyChangeTriggersAReindex(self) -> None:
        result = self.chunker.split(PARAGRAPHS, policy=self.policy)
        source = self.source(result, policySignature="PARAGRAPH|999|0|0")
        plan = self.planner.plan(source, result, self.records(result))
        self.assertEqual(plan.action, "REINDEX")
        self.assertEqual(plan.reason, "Chunking policy changed.")

    def testChangedContentReportsItsReason(self) -> None:
        original = self.chunker.split(PARAGRAPHS, policy=self.policy)
        updated = self.chunker.split(f"{PARAGRAPHS}\n\nExtra paragraph here.", policy=self.policy)
        plan = self.planner.plan(self.source(original), updated, self.records(original))
        self.assertEqual(plan.reason, "Source content checksum changed.")

    def testFailedSourceIsReindexedEvenWithIdenticalContent(self) -> None:
        result = self.chunker.split(PARAGRAPHS, policy=self.policy)
        source = self.source(result, status="FAILED")
        plan = self.planner.plan(source, result, self.records(result))
        self.assertEqual(plan.action, "REINDEX")
        self.assertIn("FAILED", plan.reason)

    def testArchivedSourceCannotBePlanned(self) -> None:
        result = self.chunker.split(PARAGRAPHS, policy=self.policy)
        source = self.source(result, status="ARCHIVED")
        with self.assertRaises(ValidationFailedError):
            self.planner.plan(source, result, self.records(result))

    def testPlannerRejectsForeignInput(self) -> None:
        with self.assertRaises(AIKnowledgeSourceInvalid):
            self.planner.plan(None, "chunks")  # type: ignore[arg-type]

    def testDuplicateChunksAreNotReusedTwice(self) -> None:
        text = "Repeated paragraph body.\n\nRepeated paragraph body.\n\nUnique tail paragraph."
        original = self.chunker.split(text, policy=self.policy)
        stored = self.records(original)
        plan = self.planner.plan(self.source(original), original, stored, force=True)
        reusedIds = {chunk.id for chunk, _ in plan.reused}
        self.assertEqual(len(reusedIds), len(plan.reused))

    def testBuildChunkRecordsCarriesClassificationAndMetadata(self) -> None:
        result = self.chunker.split(PARAGRAPHS, policy=self.policy)
        records = buildChunkRecords(
            TENANT,
            SOURCE,
            result.chunks,
            classification="CONFIDENTIAL",
            metadata={"reference": "DOCUMENTS:DOCUMENT:doc-1"},
            createdAt=CLOCK,
        )
        self.assertEqual({record.classification for record in records}, {"CONFIDENTIAL"})
        self.assertEqual(records[0].metadata["reference"], "DOCUMENTS:DOCUMENT:doc-1")
        self.assertEqual({record.createdAt for record in records}, {CLOCK})


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
