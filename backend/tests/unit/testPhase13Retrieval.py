"""Phase 13-S unit tests — retrieval pipeline and reranking, fully offline.

Covers the closed vocabularies, ``RetrievalPolicy`` validation, the
deterministic lexical helpers (tokenization, query coverage, Jaccard),
reciprocal rank fusion, score normalization, the three rerank strategies
(including MMR diversity), the pipeline state machine and its stage trace,
the **structural** guarantee that context can never be assembled before
permission filtering, context budgeting and citation numbering, and the
grounded prompt rendering.

No Django, database, network, provider, or clock dependency.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime

from apps.ai.domain.exceptions import (
    AIRetrievalInvalid,
    AIRetrievalPolicyInvalid,
    AIRetrievalStageViolation,
)
from apps.ai.domain.services.retrievalPipeline import (
    DEFAULT_GROUNDING_INSTRUCTION,
    Reranker,
    RetrievalCandidate,
    RetrievalPipeline,
    RetrievalTrace,
    StageRecord,
)
from apps.ai.domain.valueObjects.retrievalTypes import (
    MAX_TOP_K,
    RERANK_STRATEGIES,
    RETRIEVAL_STAGES,
    RETRIEVAL_STRATEGIES,
    RetrievalPolicy,
    ensureRerankStrategy,
    ensureStage,
    ensureStrategy,
    jaccardSimilarity,
    lexicalOverlap,
    normalizeScores,
    reciprocalRankFusion,
    tokenize,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


def frozenClock() -> datetime:
    return CLOCK


def candidate(
    name: str,
    text: str,
    *,
    vectorScore: float = 0.0,
    lexicalScore: float = 0.0,
    classification: str = "INTERNAL",
    ordinal: int = 0,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunkId=uuid.uuid5(uuid.NAMESPACE_OID, name),
        sourceReference=f"DOCUMENTS:DOCUMENT:{name}",
        text=text,
        vectorScore=vectorScore,
        lexicalScore=lexicalScore,
        classification=classification,
        ordinal=ordinal,
        sourceDomain="DOCUMENTS",
        sourceEntityType="DOCUMENT",
        sourceEntityId=name,
    )


class VocabularyTests(unittest.TestCase):
    def testClosedVocabulariesAreStable(self) -> None:
        self.assertEqual(RETRIEVAL_STRATEGIES, ("VECTOR", "LEXICAL", "HYBRID"))
        self.assertEqual(RERANK_STRATEGIES, ("NONE", "LEXICAL_BOOST", "MMR"))
        self.assertEqual(
            RETRIEVAL_STAGES,
            ("EMBED", "CANDIDATES", "RESOLVE", "AUTHORIZE", "RERANK", "CONTEXT", "ANSWER"),
        )

    def testValuesAreNormalizedAndValidated(self) -> None:
        self.assertEqual(ensureStrategy(" hybrid "), "HYBRID")
        self.assertEqual(ensureRerankStrategy("mmr"), "MMR")
        self.assertEqual(ensureStage("context"), "CONTEXT")
        with self.assertRaises(ValidationFailedError):
            ensureStrategy("SEMANTIC")
        with self.assertRaises(ValidationFailedError):
            ensureStage("GENERATE")


class LexicalMathTests(unittest.TestCase):
    def testTokenizationIsCaseFoldedAndLanguageNeutral(self) -> None:
        self.assertEqual(tokenize("Quarterly, REPORT!"), ("quarterly", "report"))
        self.assertEqual(tokenize("گزارش سه‌ماهه"), ("گزارش", "سه", "ماهه"))
        self.assertEqual(tokenize("  "), ())

    def testQueryCoverageIsBoundedAndDirectional(self) -> None:
        self.assertEqual(lexicalOverlap("production line", "the production line halted"), 1.0)
        self.assertEqual(lexicalOverlap("production line", "the production halted"), 0.5)
        self.assertEqual(lexicalOverlap("production", "nothing relevant"), 0.0)
        self.assertEqual(lexicalOverlap("", "anything"), 0.0)
        self.assertEqual(lexicalOverlap("query", ""), 0.0)

    def testLongDocumentsAreNotRewardedForLength(self) -> None:
        short = lexicalOverlap("safety policy", "safety policy")
        padded = lexicalOverlap("safety policy", "safety policy " + "filler " * 50)
        self.assertEqual(short, padded)

    def testJaccardIsSymmetricAndBounded(self) -> None:
        self.assertEqual(jaccardSimilarity("alpha beta", "beta alpha"), 1.0)
        self.assertEqual(jaccardSimilarity("alpha", "beta"), 0.0)
        self.assertEqual(
            jaccardSimilarity("alpha beta", "beta gamma"),
            jaccardSimilarity("beta gamma", "alpha beta"),
        )
        self.assertEqual(jaccardSimilarity("", "beta"), 0.0)

    def testRankFusionRewardsAgreementBetweenLists(self) -> None:
        fused = reciprocalRankFusion([["a", "b", "c"], ["c", "a", "b"]])
        self.assertGreater(fused["a"], fused["b"])
        self.assertGreater(fused["c"], fused["b"])

    def testRankFusionIsRankBasedNotScoreBased(self) -> None:
        onlyFirst = reciprocalRankFusion([["a"], []])
        self.assertEqual(list(onlyFirst), ["a"])
        with self.assertRaises(ValidationFailedError):
            reciprocalRankFusion([["a"]], constant=0)

    def testNormalizationMapsIntoUnitRange(self) -> None:
        self.assertEqual(normalizeScores([1.0, 3.0, 5.0]), (0.0, 0.5, 1.0))
        self.assertEqual(normalizeScores([2.0, 2.0]), (1.0, 1.0))
        self.assertEqual(normalizeScores([]), ())


class RetrievalPolicyTests(unittest.TestCase):
    def testDefaultsAreCoherent(self) -> None:
        policy = RetrievalPolicy()
        self.assertEqual(policy.strategy, "HYBRID")
        self.assertTrue(policy.usesVectors)
        self.assertTrue(policy.usesLexical)
        self.assertTrue(policy.requireGrounding)
        self.assertIn("HYBRID", policy.signature())

    def testStrategyFlagsFollowTheStrategy(self) -> None:
        self.assertTrue(RetrievalPolicy(strategy="VECTOR").usesVectors)
        self.assertFalse(RetrievalPolicy(strategy="VECTOR").usesLexical)
        self.assertTrue(RetrievalPolicy(strategy="LEXICAL").usesLexical)
        self.assertFalse(RetrievalPolicy(strategy="LEXICAL").usesVectors)

    def testBoundsAreEnforced(self) -> None:
        with self.assertRaises(ValidationFailedError):
            RetrievalPolicy(topK=0)
        with self.assertRaises(ValidationFailedError):
            RetrievalPolicy(topK=MAX_TOP_K + 1)
        with self.assertRaises(ValidationFailedError):
            RetrievalPolicy(topK=10, candidateLimit=5)
        with self.assertRaises(ValidationFailedError):
            RetrievalPolicy(lexicalWeight=1.5)
        with self.assertRaises(ValidationFailedError):
            RetrievalPolicy(mmrLambda=-0.1)
        with self.assertRaises(ValidationFailedError):
            RetrievalPolicy(maxContextTokens=0)
        with self.assertRaises(ValidationFailedError):
            RetrievalPolicy(minScore=2.0)
        with self.assertRaises(ValidationFailedError):
            RetrievalPolicy(requireGrounding="yes")  # type: ignore[arg-type]


class RetrievalCandidateTests(unittest.TestCase):
    def testCandidateDerivesTokensAndKeepsIdentity(self) -> None:
        item = candidate("doc-1", "line one reached ninety two percent")
        self.assertGreater(item.tokenCount, 0)
        self.assertEqual(item.key, str(item.chunkId))
        self.assertEqual(item.sourceReference, "DOCUMENTS:DOCUMENT:doc-1")

    def testCandidateRejectsEmptyTextOrReference(self) -> None:
        with self.assertRaises(AIRetrievalInvalid):
            RetrievalCandidate(chunkId=uuid.uuid4(), sourceReference="a:b:c", text="   ")
        with self.assertRaises(AIRetrievalInvalid):
            RetrievalCandidate(chunkId=uuid.uuid4(), sourceReference="", text="body")

    def testScoredReturnsACopyAndLeavesTheOriginalIntact(self) -> None:
        item = candidate("doc-1", "body text")
        updated = item.scored(finalScore=0.9)
        self.assertEqual(updated.finalScore, 0.9)
        self.assertEqual(item.finalScore, 0.0)
        self.assertEqual(updated.chunkId, item.chunkId)


class RerankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.reranker = Reranker()
        self.query = "production line output"

    def testNoneStrategyKeepsRetrievalOrder(self) -> None:
        items = [
            candidate("low", "unrelated maintenance notes", vectorScore=0.2),
            candidate("high", "production line output rose", vectorScore=0.9),
        ]
        ranked = self.reranker.rank(self.query, items, RetrievalPolicy(rerank="NONE"))
        self.assertEqual([item.sourceEntityId for item in ranked], ["high", "low"])

    def testLexicalBoostPromotesTheKeywordMatch(self) -> None:
        items = [
            candidate("vectorish", "an unrelated paragraph about weather", vectorScore=0.90),
            candidate("keyword", "production line output rose sharply", vectorScore=0.85),
        ]
        policy = RetrievalPolicy(rerank="LEXICAL_BOOST", lexicalWeight=0.8)
        ranked = self.reranker.rank(self.query, items, policy)
        self.assertEqual(ranked[0].sourceEntityId, "keyword")
        self.assertGreater(ranked[0].lexicalScore, ranked[1].lexicalScore)

    def testLexicalWeightZeroFallsBackToTheRetrievalScore(self) -> None:
        items = [
            candidate("vectorish", "an unrelated paragraph about weather", vectorScore=0.90),
            candidate("keyword", "production line output rose sharply", vectorScore=0.85),
        ]
        ranked = self.reranker.rank(
            self.query, items, RetrievalPolicy(rerank="LEXICAL_BOOST", lexicalWeight=0.0)
        )
        self.assertEqual(ranked[0].sourceEntityId, "vectorish")

    def testMmrPrefersDiversityOverNearDuplicates(self) -> None:
        # lambda=0.3 weights redundancy more than relevance, so the near
        # duplicate of the top hit is pushed behind the diverse block.
        items = [
            candidate("first", "production line output rose sharply", vectorScore=0.90),
            candidate("duplicate", "production line output rose sharply again", vectorScore=0.89),
            candidate("diverse", "maintenance downtime dropped by half", vectorScore=0.60),
        ]
        ranked = self.reranker.rank(self.query, items, RetrievalPolicy(rerank="MMR", mmrLambda=0.3))
        self.assertEqual(ranked[0].sourceEntityId, "first")
        self.assertEqual(ranked[1].sourceEntityId, "diverse")
        self.assertEqual(ranked[2].sourceEntityId, "duplicate")

    def testMmrLambdaTradesDiversityForRelevance(self) -> None:
        # The same input with a relevance-heavy lambda keeps the near
        # duplicate second: the knob works in both directions.
        items = [
            candidate("first", "production line output rose sharply", vectorScore=0.90),
            candidate("duplicate", "production line output rose sharply again", vectorScore=0.89),
            candidate("diverse", "maintenance downtime dropped by half", vectorScore=0.60),
        ]
        ranked = self.reranker.rank(self.query, items, RetrievalPolicy(rerank="MMR", mmrLambda=0.9))
        self.assertEqual(ranked[1].sourceEntityId, "duplicate")

    def testMmrWithLambdaOneIsPureRelevance(self) -> None:
        items = [
            candidate("first", "production line output rose sharply", vectorScore=0.90),
            candidate("duplicate", "production line output rose sharply again", vectorScore=0.89),
            candidate("diverse", "maintenance downtime dropped by half", vectorScore=0.10),
        ]
        ranked = self.reranker.rank(self.query, items, RetrievalPolicy(rerank="MMR", mmrLambda=1.0))
        self.assertEqual(ranked[-1].sourceEntityId, "diverse")

    def testRankingIsDeterministicRegardlessOfInputOrder(self) -> None:
        items = [
            candidate("alpha", "production line output rose", vectorScore=0.5),
            candidate("bravo", "production line output rose", vectorScore=0.5),
            candidate("charlie", "production line output rose", vectorScore=0.5),
        ]
        first = self.reranker.rank(self.query, items, RetrievalPolicy(rerank="LEXICAL_BOOST"))
        second = self.reranker.rank(
            self.query, list(reversed(items)), RetrievalPolicy(rerank="LEXICAL_BOOST")
        )
        self.assertEqual(
            [item.sourceEntityId for item in first], [item.sourceEntityId for item in second]
        )

    def testEmptyInputAndBadPolicy(self) -> None:
        self.assertEqual(self.reranker.rank(self.query, [], RetrievalPolicy()), ())
        with self.assertRaises(AIRetrievalPolicyInvalid):
            self.reranker.rank(self.query, [], "policy")  # type: ignore[arg-type]


class PipelineOrderingTests(unittest.TestCase):
    """The central architectural guarantee of S (§20)."""

    def setUp(self) -> None:
        self.policy = RetrievalPolicy(rerank="NONE", topK=3)
        self.items = [
            candidate("a", "production line output rose", vectorScore=0.9),
            candidate("b", "maintenance downtime dropped", vectorScore=0.5),
        ]

    def testAssemblingBeforeFilteringIsRefused(self) -> None:
        pipeline = RetrievalPipeline(self.policy, query="production", now=frozenClock)
        pipeline.recordEmbedding(used=True).withCandidates(self.items)
        with self.assertRaises(AIRetrievalStageViolation):
            pipeline.assembleContext()

    def testRerankingBeforeFilteringIsRefused(self) -> None:
        pipeline = RetrievalPipeline(self.policy, query="production", now=frozenClock)
        pipeline.withCandidates(self.items)
        with self.assertRaises(AIRetrievalStageViolation):
            pipeline.rerank()

    def testAuthorizationKeepsOnlyAllowedCandidates(self) -> None:
        pipeline = RetrievalPipeline(self.policy, query="production", now=frozenClock)
        pipeline.recordEmbedding(used=True).withCandidates(self.items)
        pipeline.authorize([self.items[0].key])
        self.assertEqual(len(pipeline.candidates), 1)
        self.assertEqual(pipeline.candidates[0].sourceEntityId, "a")
        self.assertTrue(pipeline.isAuthorized)

    def testDeniedEverythingProducesAnEmptyUngroundedPrompt(self) -> None:
        pipeline = RetrievalPipeline(self.policy, query="production", now=frozenClock)
        pipeline.recordEmbedding(used=True).withCandidates(self.items)
        pipeline.authorize([])
        prompt = pipeline.rerank().assembleContext()
        self.assertFalse(prompt.isGrounded)
        self.assertEqual(prompt.citations, ())
        self.assertEqual(prompt.contextText, "")

    def testPipelineRequiresARealPolicy(self) -> None:
        with self.assertRaises(AIRetrievalPolicyInvalid):
            RetrievalPipeline("policy", query="x")  # type: ignore[arg-type]

    def testForeignCandidateTypesAreRejected(self) -> None:
        pipeline = RetrievalPipeline(self.policy, now=frozenClock)
        with self.assertRaises(AIRetrievalInvalid):
            pipeline.withCandidates(["not a candidate"])  # type: ignore[list-item]


class PipelineFusionAndTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.vector = [
            candidate("a", "production line output rose", vectorScore=0.9),
            candidate("b", "maintenance downtime dropped", vectorScore=0.7),
        ]
        self.lexical = [
            candidate("b", "maintenance downtime dropped", lexicalScore=0.8),
            candidate("c", "production safety training completed", lexicalScore=0.4),
        ]

    def testHybridFusionMergesBothListsWithoutDuplicates(self) -> None:
        pipeline = RetrievalPipeline(RetrievalPolicy(strategy="HYBRID"), now=frozenClock)
        pipeline.withCandidates(self.vector, self.lexical)
        keys = [item.sourceEntityId for item in pipeline.candidates]
        self.assertEqual(sorted(keys), ["a", "b", "c"])
        self.assertEqual(len(keys), len(set(keys)))

    def testAgreedCandidateWinsUnderFusion(self) -> None:
        pipeline = RetrievalPipeline(RetrievalPolicy(strategy="HYBRID"), now=frozenClock)
        pipeline.withCandidates(self.vector, self.lexical)
        best = pipeline.candidates[0]
        self.assertEqual(best.sourceEntityId, "b")

    def testCandidateLimitTruncatesAfterFusion(self) -> None:
        policy = RetrievalPolicy(strategy="HYBRID", topK=1, candidateLimit=2)
        pipeline = RetrievalPipeline(policy, now=frozenClock)
        pipeline.withCandidates(self.vector, self.lexical)
        self.assertEqual(len(pipeline.candidates), 2)

    def testTraceRecordsEveryStageInOrder(self) -> None:
        pipeline = RetrievalPipeline(RetrievalPolicy(rerank="NONE"), query="q", now=frozenClock)
        pipeline.recordEmbedding(used=True)
        pipeline.withCandidates(self.vector)
        pipeline.recordResolution(len(self.vector))
        pipeline.authorize([self.vector[0].key])
        pipeline.rerank()
        pipeline.assembleContext()
        pipeline.recordAnswer(grounded=True)
        stages = [record.stage for record in pipeline.trace.stages]
        self.assertEqual(
            stages, ["EMBED", "CANDIDATES", "RESOLVE", "AUTHORIZE", "RERANK", "CONTEXT", "ANSWER"]
        )
        self.assertTrue(pipeline.trace.has("AUTHORIZE"))
        self.assertEqual(pipeline.trace.countFor("AUTHORIZE"), 1)

    def testTraceSummaryIsContentFree(self) -> None:
        pipeline = RetrievalPipeline(
            RetrievalPolicy(rerank="NONE"), query="secret", now=frozenClock
        )
        pipeline.withCandidates(self.vector)
        pipeline.authorize([self.vector[0].key])
        summary = pipeline.trace.summary()
        rendered = str(summary)
        self.assertNotIn("production line output", rendered)
        self.assertIn("stages", summary)
        self.assertEqual(summary["stages"][0]["stage"], "CANDIDATES")

    def testStageRecordComputesDroppedCount(self) -> None:
        record = StageRecord(stage="AUTHORIZE", inputCount=10, outputCount=4)
        self.assertEqual(record.droppedCount, 6)
        with self.assertRaises(ValidationFailedError):
            StageRecord(stage="UNKNOWN", inputCount=1, outputCount=1)

    def testEmptyTraceReportsMissingStages(self) -> None:
        trace = RetrievalTrace(query="q", policySignature="sig")
        self.assertFalse(trace.has("CONTEXT"))
        self.assertEqual(trace.countFor("CONTEXT"), 0)


class ContextAssemblyTests(unittest.TestCase):
    def build(self, policy: RetrievalPolicy, items: list[RetrievalCandidate]) -> RetrievalPipeline:
        pipeline = RetrievalPipeline(policy, query="production line output", now=frozenClock)
        pipeline.recordEmbedding(used=True).withCandidates(items)
        pipeline.authorize([item.key for item in items])
        pipeline.rerank()
        return pipeline

    def testCitationsAreNumberedFromOneInRankOrder(self) -> None:
        items = [
            candidate("a", "production line output rose", vectorScore=0.9),
            candidate("b", "production output stable", vectorScore=0.6),
        ]
        prompt = self.build(RetrievalPolicy(rerank="NONE"), items).assembleContext()
        self.assertEqual([citation.index for citation in prompt.citations], [1, 2])
        self.assertEqual(prompt.citations[0].sourceReference, "DOCUMENTS:DOCUMENT:a")
        self.assertIn("[1] (DOCUMENTS:DOCUMENT:a)", prompt.contextText)

    def testTopKLimitsTheEvidence(self) -> None:
        items = [
            candidate(
                f"doc{index}", f"production line output {index}", vectorScore=1.0 - index / 10
            )
            for index in range(6)
        ]
        prompt = self.build(RetrievalPolicy(rerank="NONE", topK=2), items).assembleContext()
        self.assertEqual(len(prompt.citations), 2)

    def testTokenBudgetStopsPackingButKeepsTheBestBlock(self) -> None:
        long = "word " * 400
        items = [
            candidate("a", f"production {long}", vectorScore=0.9),
            candidate("b", f"output {long}", vectorScore=0.8),
        ]
        policy = RetrievalPolicy(rerank="NONE", maxContextTokens=200)
        prompt = self.build(policy, items).assembleContext()
        self.assertEqual(len(prompt.citations), 1)
        self.assertGreater(prompt.tokenCount, 0)

    def testMaxContextSourcesIsHonoured(self) -> None:
        items = [
            candidate(f"doc{index}", f"production output {index}", vectorScore=0.5)
            for index in range(5)
        ]
        policy = RetrievalPolicy(rerank="NONE", topK=5, maxContextSources=2)
        prompt = self.build(policy, items).assembleContext()
        self.assertEqual(len(prompt.citations), 2)

    def testDedupeBySourceKeepsOneBlockPerDocument(self) -> None:
        first = candidate("shared", "production line output rose", vectorScore=0.9, ordinal=0)
        second = candidate("shared", "production line output fell", vectorScore=0.8, ordinal=1)
        second = RetrievalCandidate(
            chunkId=uuid.uuid5(uuid.NAMESPACE_OID, "shared-2"),
            sourceReference=first.sourceReference,
            text="production line output fell",
            vectorScore=0.8,
            sourceDomain="DOCUMENTS",
            sourceEntityType="DOCUMENT",
            sourceEntityId="shared",
            ordinal=1,
        )
        policy = RetrievalPolicy(rerank="NONE", dedupeBySource=True, topK=5)
        prompt = self.build(policy, [first, second]).assembleContext()
        self.assertEqual(len(prompt.citations), 1)

    def testMinScoreFiltersWeakEvidenceBeforeAssembly(self) -> None:
        items = [
            candidate("strong", "production line output rose", vectorScore=1.0),
            candidate("weak", "an unrelated note", vectorScore=0.0),
        ]
        policy = RetrievalPolicy(rerank="LEXICAL_BOOST", minScore=0.5, topK=5)
        prompt = self.build(policy, items).assembleContext()
        self.assertEqual(
            [citation.sourceReference for citation in prompt.citations],
            ["DOCUMENTS:DOCUMENT:strong"],
        )

    def testPromptRendersInstructionContextAndQuestion(self) -> None:
        items = [candidate("a", "production line output rose", vectorScore=0.9)]
        prompt = self.build(RetrievalPolicy(rerank="NONE"), items).assembleContext(
            question="what happened to output?"
        )
        rendered = prompt.render()
        self.assertIn(DEFAULT_GROUNDING_INSTRUCTION, rendered)
        self.assertIn("[1]", rendered)
        self.assertIn("what happened to output?", rendered)
        self.assertTrue(prompt.isGrounded)

    def testUngroundedPromptSaysSoInsteadOfPretending(self) -> None:
        pipeline = RetrievalPipeline(RetrievalPolicy(rerank="NONE"), query="q", now=frozenClock)
        pipeline.withCandidates([])
        pipeline.authorize([])
        prompt = pipeline.rerank().assembleContext()
        self.assertIn("(no authorized context)", prompt.render())
        self.assertFalse(prompt.isGrounded)

    def testCustomInstructionOverridesTheDefault(self) -> None:
        items = [candidate("a", "production line output rose", vectorScore=0.9)]
        prompt = self.build(RetrievalPolicy(rerank="NONE"), items).assembleContext(
            instruction="Reply in Persian only."
        )
        self.assertIn("Reply in Persian only.", prompt.render())
        self.assertNotIn(DEFAULT_GROUNDING_INSTRUCTION, prompt.render())


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
