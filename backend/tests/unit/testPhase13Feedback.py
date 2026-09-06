"""Phase 13-V unit tests — feedback vocabularies, entity, engine. Offline.

Covers the closed vocabularies and their reason→metric mapping, rating
normalization and sentiment derivation, the idempotency fingerprint, the
aggregation math (satisfaction, net sentiment, reason ranking), the
``FeedbackPolicy`` that decides promotion, the entity with its triage
lifecycle and golden-case projection plus the Phase 13-B bridge, the
aggregator with its per-target breakdown, the trend comparer, and the
promotion planner (grouping, thresholds, and every skip reason).

No Django, database, network, provider, or clock dependency.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from apps.ai.domain.entities.aiRecords import AIFeedback
from apps.ai.domain.entities.feedbackRecords import AIFeedbackEntry
from apps.ai.domain.exceptions import AIFeedbackInvalid, AIFeedbackPolicyInvalid
from apps.ai.domain.services.feedbackEngine import (
    FeedbackAggregator,
    FeedbackSummary,
    PromotionPlanner,
    TrendComparer,
)
from apps.ai.domain.valueObjects.feedbackTypes import (
    FEEDBACK_KINDS,
    FEEDBACK_REASONS,
    FEEDBACK_STATUSES,
    FeedbackPolicy,
    clampText,
    coherentSentiment,
    ensureFeedbackKind,
    ensureFeedbackReason,
    ensureFeedbackStatus,
    feedbackFingerprint,
    metricForReason,
    netSentiment,
    normalizeRating,
    rankReasons,
    satisfactionScore,
    sentimentForRating,
    sentimentWeight,
    summarizeWeights,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
REQUEST = uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
RESPONSE = uuid.UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
USER = uuid.UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
OTHER_USER = uuid.UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")


def entry(**overrides: object) -> AIFeedbackEntry:
    params: dict = {
        "tenantId": TENANT,
        "requestId": REQUEST,
        "responseId": RESPONSE,
        "userId": USER,
        "kind": "RATING",
        "rating": 2,
        "reason": "UNGROUNDED",
        "correction": "Line one reached ninety two percent.",
        "question": "what was the production output",
        "modelCode": "GPT_TEST",
        "promptVersion": "3",
        "createdAt": CLOCK,
        "updatedAt": CLOCK,
    }
    params.update(overrides)
    return AIFeedbackEntry(**params)


class VocabularyTests(unittest.TestCase):
    def testClosedVocabulariesAreStable(self) -> None:
        self.assertEqual(FEEDBACK_KINDS, ("RATING", "THUMBS", "CORRECTION", "FLAG", "COMMENT"))
        self.assertIn("UNGROUNDED", FEEDBACK_REASONS)
        self.assertIn("UNSAFE", FEEDBACK_REASONS)
        self.assertEqual(FEEDBACK_STATUSES, ("NEW", "TRIAGED", "ACCEPTED", "REJECTED", "PROMOTED"))

    def testValuesAreNormalized(self) -> None:
        self.assertEqual(ensureFeedbackKind(" thumbs "), "THUMBS")
        self.assertEqual(ensureFeedbackReason("unsafe"), "UNSAFE")
        self.assertEqual(ensureFeedbackStatus("promoted"), "PROMOTED")
        with self.assertRaises(ValidationFailedError):
            ensureFeedbackKind("EMOJI")
        with self.assertRaises(ValidationFailedError):
            ensureFeedbackReason("VIBES")

    def testEveryActionableReasonMapsOntoAnEvaluationMetric(self) -> None:
        self.assertEqual(metricForReason("UNGROUNDED"), "GROUNDEDNESS")
        self.assertEqual(metricForReason("UNSAFE"), "SAFETY")
        self.assertEqual(metricForReason("OFF_TOPIC"), "RELEVANCE")
        self.assertEqual(metricForReason("TOO_SLOW"), "LATENCY")
        self.assertEqual(metricForReason("OTHER"), "")

    def testTextClampingGuardsTheStore(self) -> None:
        self.assertEqual(clampText("  hi  ", 10, "comment"), "hi")
        with self.assertRaises(ValidationFailedError):
            clampText("x" * 20, 10, "comment")


class RatingAndSentimentTests(unittest.TestCase):
    def testRatingRangeIsEnforced(self) -> None:
        self.assertEqual(normalizeRating(3), 3)
        self.assertIsNone(normalizeRating(None))
        for bad in (0, 6, -1):
            with self.assertRaises(ValidationFailedError):
                normalizeRating(bad)
        with self.assertRaises(ValidationFailedError):
            normalizeRating(True)

    def testRatingMapsOntoSentimentWithOneStatedCutoff(self) -> None:
        self.assertEqual(sentimentForRating(5), "POSITIVE")
        self.assertEqual(sentimentForRating(4), "POSITIVE")
        self.assertEqual(sentimentForRating(3), "NEUTRAL")
        self.assertEqual(sentimentForRating(2), "NEGATIVE")
        self.assertEqual(sentimentForRating(1), "NEGATIVE")
        self.assertEqual(sentimentForRating(None), "NEUTRAL")

    def testSentimentWeightsAreSymmetric(self) -> None:
        self.assertEqual(sentimentWeight("POSITIVE"), 1.0)
        self.assertEqual(sentimentWeight("NEUTRAL"), 0.0)
        self.assertEqual(sentimentWeight("NEGATIVE"), -1.0)

    def testCoherentSentimentPrefersTheExplicitValue(self) -> None:
        self.assertEqual(coherentSentiment("RATING", 5, "NEGATIVE"), "NEGATIVE")
        self.assertEqual(coherentSentiment("RATING", 5, ""), "POSITIVE")

    def testKindImpliesSentimentWhenNothingElseDoes(self) -> None:
        self.assertEqual(coherentSentiment("FLAG", None, ""), "NEGATIVE")
        self.assertEqual(coherentSentiment("CORRECTION", None, ""), "NEGATIVE")
        self.assertEqual(coherentSentiment("COMMENT", None, ""), "NEUTRAL")
        self.assertEqual(coherentSentiment("THUMBS", None, ""), "NEUTRAL")


class FingerprintTests(unittest.TestCase):
    def testOneSignalPerUserPerResponsePerKind(self) -> None:
        first = feedbackFingerprint(REQUEST, USER, "RATING", responseId=RESPONSE)
        again = feedbackFingerprint(REQUEST, USER, "RATING", responseId=RESPONSE)
        self.assertEqual(first, again)
        self.assertEqual(len(first), 64)

    def testDifferentUsersKindsAndResponsesDiffer(self) -> None:
        base = feedbackFingerprint(REQUEST, USER, "RATING", responseId=RESPONSE)
        self.assertNotEqual(
            base, feedbackFingerprint(REQUEST, OTHER_USER, "RATING", responseId=RESPONSE)
        )
        self.assertNotEqual(base, feedbackFingerprint(REQUEST, USER, "FLAG", responseId=RESPONSE))
        self.assertNotEqual(base, feedbackFingerprint(REQUEST, USER, "RATING"))

    def testAnonymousSignalsShareOneSlot(self) -> None:
        self.assertEqual(
            feedbackFingerprint(REQUEST, None, "RATING"),
            feedbackFingerprint(REQUEST, None, "RATING"),
        )


class AggregationMathTests(unittest.TestCase):
    def testSatisfactionRescalesTheMeanRating(self) -> None:
        self.assertEqual(satisfactionScore([5, 5]), 1.0)
        self.assertEqual(satisfactionScore([1, 1]), 0.0)
        self.assertEqual(satisfactionScore([3]), 0.5)
        self.assertEqual(satisfactionScore([]), 0.0)

    def testNetSentimentIsBounded(self) -> None:
        self.assertEqual(netSentiment(["POSITIVE", "POSITIVE"]), 1.0)
        self.assertEqual(netSentiment(["POSITIVE", "NEGATIVE"]), 0.0)
        self.assertEqual(netSentiment(["NEGATIVE"]), -1.0)
        self.assertEqual(netSentiment([]), 0.0)

    def testReasonsAreRankedByFrequencyThenName(self) -> None:
        ranked = rankReasons(["UNGROUNDED", "UNSAFE", "UNGROUNDED", "", "OFF_TOPIC"])
        self.assertEqual(ranked[0], ("UNGROUNDED", 2))
        self.assertEqual([reason for reason, _ in ranked[1:]], ["OFF_TOPIC", "UNSAFE"])

    def testPreAggregatedCountsProduceTheSameNetSentiment(self) -> None:
        self.assertEqual(summarizeWeights({"POSITIVE": 3, "NEGATIVE": 1}), 0.5)
        self.assertEqual(summarizeWeights({}), 0.0)


class PolicyTests(unittest.TestCase):
    def testDefaultsAreConservative(self) -> None:
        policy = FeedbackPolicy()
        self.assertEqual(policy.promotionThreshold, 2)
        self.assertTrue(policy.requireCorrection)
        self.assertTrue(policy.requireReason)
        self.assertTrue(policy.isNegativeRating(2))
        self.assertFalse(policy.isNegativeRating(3))
        self.assertFalse(policy.isNegativeRating(None))

    def testRangesAreEnforced(self) -> None:
        with self.assertRaises(ValidationFailedError):
            FeedbackPolicy(promotionThreshold=0)
        with self.assertRaises(ValidationFailedError):
            FeedbackPolicy(negativeRatingCeiling=9)
        with self.assertRaises(ValidationFailedError):
            FeedbackPolicy(minimumSatisfaction=1.5)
        with self.assertRaises(ValidationFailedError):
            FeedbackPolicy(requireReason="yes")  # type: ignore[arg-type]

    def testSignatureChangesWithThePolicy(self) -> None:
        self.assertNotEqual(
            FeedbackPolicy().signature(), FeedbackPolicy(promotionThreshold=5).signature()
        )


class FeedbackEntryTests(unittest.TestCase):
    def testEntryDerivesSentimentFingerprintAndTarget(self) -> None:
        item = entry()
        self.assertEqual(item.sentiment, "NEGATIVE")
        self.assertEqual(item.targetKey, "GPT_TEST@3")
        self.assertEqual(len(item.fingerprint), 64)
        self.assertEqual(item.status, "NEW")
        self.assertEqual(item.suggestedMetric(), "GROUNDEDNESS")

    def testKindSpecificRequirements(self) -> None:
        with self.assertRaises(ValidationFailedError):
            entry(kind="RATING", rating=None)
        with self.assertRaises(ValidationFailedError):
            entry(kind="CORRECTION", correction="", rating=None)
        self.assertEqual(
            entry(kind="THUMBS", rating=None, sentiment="POSITIVE").sentiment, "POSITIVE"
        )

    def testGuardsRejectOversizedText(self) -> None:
        with self.assertRaises(ValidationFailedError):
            entry(comment="x" * 5000)
        with self.assertRaises(ValidationFailedError):
            entry(correction="x" * 9000)
        with self.assertRaises(ValidationFailedError):
            entry(metadata=["nope"])

    def testTriageLifecycleFollowsItsMachine(self) -> None:
        item = entry()
        item.accept(reviewerId=USER, now=CLOCK)
        self.assertEqual(item.status, "ACCEPTED")
        self.assertEqual(item.triagedBy, USER)
        item.promote("FEEDBACK_001", now=CLOCK)
        self.assertEqual(item.status, "PROMOTED")
        self.assertEqual(item.promotedCaseCode, "FEEDBACK_001")
        self.assertTrue(item.isTerminal)

    def testRejectionRequiresAReason(self) -> None:
        item = entry()
        with self.assertRaises(ValidationFailedError):
            item.reject("   ", now=CLOCK)
        item.reject("Duplicate of an existing report.", now=CLOCK)
        self.assertEqual(item.status, "REJECTED")
        self.assertTrue(item.rejectionReason)

    def testAnAutomatedSweepMayPromoteWithoutManualTriage(self) -> None:
        # Promotion implies acceptance: the promotion policy is a stricter
        # gate than manual triage, so a sweep may go NEW → PROMOTED.
        item = entry()
        item.promote("CASE", now=CLOCK)
        self.assertEqual(item.status, "PROMOTED")

    def testATerminalSignalCannotBeResurrected(self) -> None:
        rejected = entry()
        rejected.reject("no", now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            rejected.accept(now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            rejected.promote("CASE", now=CLOCK)
        promoted = entry()
        promoted.promote("CASE", now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            promoted.reject("changed my mind", now=CLOCK)

    def testRevisionUpdatesTheSameSlot(self) -> None:
        item = entry(rating=2)
        item.revise(rating=5, now=CLOCK + timedelta(minutes=1))
        self.assertEqual(item.rating, 5)
        self.assertEqual(item.sentiment, "POSITIVE")
        self.assertEqual(item.updatedAt, CLOCK + timedelta(minutes=1))

    def testATerminalSignalCannotBeRevised(self) -> None:
        item = entry()
        item.reject("no", now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            item.revise(rating=5, now=CLOCK)

    def testPromotabilityFollowsThePolicy(self) -> None:
        policy = FeedbackPolicy()
        self.assertTrue(entry().isPromotable(policy))
        self.assertFalse(entry(rating=5, reason="", correction="").isPromotable(policy))
        self.assertFalse(entry(correction="").isPromotable(policy))
        self.assertFalse(entry(reason="").isPromotable(policy))
        self.assertFalse(entry(question="").isPromotable(policy))
        relaxed = FeedbackPolicy(requireCorrection=False, requireReason=False)
        self.assertTrue(entry(correction="", reason="").isPromotable(relaxed))

    def testGoldenCaseDraftCarriesTheProvenance(self) -> None:
        draft = entry().toGoldenCaseDraft(suiteCode="feedback_golden")
        self.assertEqual(draft["suiteCode"], "FEEDBACK_GOLDEN")
        self.assertEqual(draft["question"], "what was the production output")
        self.assertEqual(draft["expectedTerms"], ("Line one reached ninety two percent.",))
        self.assertEqual(draft["metadata"]["origin"], "FEEDBACK")
        self.assertEqual(draft["metadata"]["metric"], "GROUNDEDNESS")
        self.assertEqual(draft["metadata"]["modelCode"], "GPT_TEST")

    def testDraftRefusesWithoutTheOriginalQuestion(self) -> None:
        with self.assertRaises(ValidationFailedError):
            entry(question="").toGoldenCaseDraft()

    def testBridgeToPhase13BFeedback(self) -> None:
        bridged = entry().toDomainFeedback()
        self.assertIsInstance(bridged, AIFeedback)
        self.assertEqual(bridged.rating, 2)
        self.assertEqual(bridged.sentiment, "NEGATIVE")

    def testBridgeRefusesWithoutAResponseId(self) -> None:
        with self.assertRaises(ValidationFailedError):
            entry(responseId=None).toDomainFeedback()


class AggregatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregator = FeedbackAggregator()

    def testEmptyStreamProducesAnEmptySummary(self) -> None:
        summary = self.aggregator.summarize([])
        self.assertTrue(summary.isEmpty)
        self.assertEqual(summary.satisfaction, 0.0)
        self.assertEqual(summary.negativeRatio, 0.0)

    def testCountsAndScoresReflectTheStream(self) -> None:
        summary = self.aggregator.summarize(
            [
                entry(rating=5, reason="", correction=""),
                entry(rating=4, userId=OTHER_USER, reason="", correction=""),
                entry(rating=1, userId=None),
            ]
        )
        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.positive, 2)
        self.assertEqual(summary.negative, 1)
        self.assertEqual(summary.ratedCount, 3)
        self.assertAlmostEqual(summary.satisfaction, 0.583333, places=5)
        self.assertAlmostEqual(summary.netSentiment, 0.333333, places=5)
        self.assertAlmostEqual(summary.negativeRatio, 0.333333, places=5)

    def testReasonsAreRankedInTheSummary(self) -> None:
        summary = self.aggregator.summarize(
            [entry(), entry(userId=OTHER_USER), entry(userId=None, reason="UNSAFE")]
        )
        self.assertEqual(summary.topReasons[0], ("UNGROUNDED", 2))

    def testTargetsAreBrokenDownByModelAndPromptVersion(self) -> None:
        summary = self.aggregator.summarize(
            [
                entry(rating=5, reason="", correction=""),
                entry(rating=1, modelCode="GPT_TEST", promptVersion="4", userId=OTHER_USER),
            ]
        )
        keys = [target.targetKey for target in summary.targets]
        self.assertEqual(keys, ["GPT_TEST@3", "GPT_TEST@4"])
        self.assertEqual(summary.targets[0].positive, 1)
        self.assertEqual(summary.targets[1].negative, 1)

    def testUnknownProvenanceStillGroups(self) -> None:
        summary = self.aggregator.summarize([entry(modelCode="", promptVersion="")])
        self.assertEqual(summary.targets[0].targetKey, "UNKNOWN_MODEL@-")

    def testSatisfactionBarIsCheckedAgainstThePolicy(self) -> None:
        good = self.aggregator.summarize([entry(rating=5, reason="", correction="")])
        bad = self.aggregator.summarize([entry(rating=1)])
        self.assertTrue(good.meets(FeedbackPolicy()))
        self.assertFalse(bad.meets(FeedbackPolicy()))
        self.assertTrue(FeedbackSummary().meets(FeedbackPolicy()))
        with self.assertRaises(AIFeedbackPolicyInvalid):
            good.meets("policy")  # type: ignore[arg-type]

    def testForeignInputIsRejected(self) -> None:
        with self.assertRaises(AIFeedbackInvalid):
            self.aggregator.summarize(["feedback"])  # type: ignore[list-item]


class TrendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregator = FeedbackAggregator()
        self.comparer = TrendComparer()
        self.policy = FeedbackPolicy()

    def window(self, *ratings: int) -> FeedbackSummary:
        return self.aggregator.summarize(
            [
                entry(rating=rating, userId=uuid.uuid4(), reason="", correction="")
                for rating in ratings
            ]
        )

    def testStableWindowsShowNoMovement(self) -> None:
        trend = self.comparer.compare(self.window(4, 4), self.window(4, 4), self.policy)
        self.assertFalse(trend.regressed)
        self.assertFalse(trend.improved)
        self.assertEqual(trend.satisfactionDelta, 0.0)

    def testDroppingSatisfactionIsARegression(self) -> None:
        trend = self.comparer.compare(self.window(5, 5), self.window(1, 2), self.policy)
        self.assertTrue(trend.regressed)
        self.assertLess(trend.satisfactionDelta, 0)
        self.assertIn("tolerance", trend.reason)

    def testRisingSatisfactionIsAnImprovement(self) -> None:
        trend = self.comparer.compare(self.window(1, 2), self.window(5, 5), self.policy)
        self.assertTrue(trend.improved)
        self.assertFalse(trend.regressed)

    def testAnEmptyWindowIsNeverARegression(self) -> None:
        trend = self.comparer.compare(FeedbackSummary(), self.window(1), self.policy)
        self.assertFalse(trend.regressed)
        self.assertIn("no feedback", trend.reason)

    def testNewReasonsAreSurfaced(self) -> None:
        baseline = self.aggregator.summarize([entry(reason="UNGROUNDED")])
        candidate = self.aggregator.summarize(
            [entry(reason="UNSAFE", userId=OTHER_USER), entry(reason="UNGROUNDED")]
        )
        trend = self.comparer.compare(baseline, candidate, self.policy)
        self.assertIn("UNSAFE", trend.newReasons)

    def testForeignInputIsRejected(self) -> None:
        with self.assertRaises(AIFeedbackPolicyInvalid):
            self.comparer.compare(FeedbackSummary(), FeedbackSummary(), "policy")  # type: ignore[arg-type]
        with self.assertRaises(AIFeedbackInvalid):
            self.comparer.compare("summary", FeedbackSummary(), self.policy)  # type: ignore[arg-type]


class PromotionPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = PromotionPlanner()
        self.policy = FeedbackPolicy()

    def complaint(self, **overrides: object) -> AIFeedbackEntry:
        params: dict = {"userId": uuid.uuid4()}
        params.update(overrides)
        return entry(**params)

    def testARepeatedComplaintBecomesOneDraft(self) -> None:
        plan = self.planner.plan([self.complaint(), self.complaint()], self.policy)
        self.assertEqual(plan.draftCount, 1)
        draft = plan.drafts[0]
        self.assertEqual(draft.occurrences, 2)
        self.assertTrue(draft.isRecurring)
        self.assertEqual(draft.metric, "GROUNDEDNESS")
        self.assertEqual(len(draft.feedbackIds), 2)

    def testASingleComplaintWaitsForTheThreshold(self) -> None:
        plan = self.planner.plan([self.complaint()], self.policy)
        self.assertEqual(plan.draftCount, 0)
        self.assertEqual(plan.skippedCount, 1)
        self.assertIn("threshold", plan.skipped[0][1])

    def testALowerThresholdPromotesImmediately(self) -> None:
        plan = self.planner.plan([self.complaint()], FeedbackPolicy(promotionThreshold=1))
        self.assertEqual(plan.draftCount, 1)

    def testPositiveSignalsAreNeverPromoted(self) -> None:
        plan = self.planner.plan(
            [self.complaint(rating=5, reason="", correction="")],
            FeedbackPolicy(promotionThreshold=1),
        )
        self.assertEqual(plan.draftCount, 0)
        self.assertIn("negative", plan.skipped[0][1])

    def testMissingReasonCorrectionOrQuestionBlocksPromotion(self) -> None:
        cases = {
            "reason": self.complaint(reason=""),
            "correction": self.complaint(correction=""),
            "question": self.complaint(question=""),
        }
        for label, item in cases.items():
            plan = self.planner.plan([item], FeedbackPolicy(promotionThreshold=1))
            self.assertEqual(plan.draftCount, 0, label)
            self.assertEqual(plan.skippedCount, 1, label)

    def testTerminalSignalsAreSkipped(self) -> None:
        promoted = self.complaint()
        promoted.accept(now=CLOCK)
        promoted.promote("EXISTING", now=CLOCK)
        plan = self.planner.plan([promoted], FeedbackPolicy(promotionThreshold=1))
        self.assertEqual(plan.draftCount, 0)
        self.assertIn("already promoted", plan.skipped[0][1])

    def testAnAlreadyCoveredQuestionIsSkipped(self) -> None:
        plan = self.planner.plan(
            [self.complaint()],
            FeedbackPolicy(promotionThreshold=1),
            knownQuestions=("What was the PRODUCTION output",),
        )
        self.assertEqual(plan.draftCount, 0)
        self.assertIn("already covers", plan.skipped[0][1])

    def testDifferentReasonsOnOneQuestionProduceSeparateDrafts(self) -> None:
        plan = self.planner.plan(
            [self.complaint(reason="UNGROUNDED"), self.complaint(reason="INCOMPLETE")],
            FeedbackPolicy(promotionThreshold=1),
        )
        self.assertEqual(plan.draftCount, 2)
        self.assertEqual({draft.reason for draft in plan.drafts}, {"UNGROUNDED", "INCOMPLETE"})

    def testDraftsAreOrderedByHowOftenTheProblemWasReported(self) -> None:
        plan = self.planner.plan(
            [
                self.complaint(reason="UNGROUNDED"),
                self.complaint(reason="UNGROUNDED"),
                self.complaint(reason="INCOMPLETE"),
            ],
            FeedbackPolicy(promotionThreshold=1),
        )
        self.assertEqual(plan.drafts[0].reason, "UNGROUNDED")
        self.assertEqual(plan.drafts[0].occurrences, 2)

    def testForeignInputIsRejected(self) -> None:
        with self.assertRaises(AIFeedbackPolicyInvalid):
            self.planner.plan([], "policy")  # type: ignore[arg-type]
        with self.assertRaises(AIFeedbackInvalid):
            self.planner.plan(["feedback"], self.policy)  # type: ignore[list-item]


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
