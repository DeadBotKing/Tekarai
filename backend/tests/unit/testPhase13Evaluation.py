"""Phase 13-U unit tests — evaluation metrics, criteria, engine. Offline.

Covers the closed vocabularies, the scoring math (coverage, groundedness,
budget ratios, weighted averages), ``MetricThreshold``/``EvaluationCriteria``
— the objects that answer Open Question #9 — the three entities with their
lifecycle guards and the Phase 13-B bridge, every metric of the engine,
the judge (required metrics, failure bands, minimum overall score), the run
aggregator, and the regression detector.

No Django, database, network, provider, or clock dependency.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime

from apps.ai.domain.entities.aiRecords import AIEvaluation
from apps.ai.domain.entities.evaluationRecords import (
    AIEvaluationCase,
    AIEvaluationResult,
    AIEvaluationRun,
    ensureCode,
)
from apps.ai.domain.exceptions import (
    AIEvaluationCriteriaInvalid,
    AIEvaluationInvalid,
)
from apps.ai.domain.services.evaluationEngine import (
    CaseObservation,
    EvaluationEngine,
    EvaluationJudge,
    RunAggregator,
    RunSummary,
    compareRuns,
)
from apps.ai.domain.valueObjects.evaluationTypes import (
    EVALUATION_METRICS,
    EVALUATION_VERDICTS,
    RUN_STATUSES,
    EvaluationCriteria,
    MetricScore,
    MetricThreshold,
    budgetScore,
    clampScore,
    coverageScore,
    ensureMetric,
    ensureVerdict,
    groundednessScore,
    weightedAverage,
    worstVerdict,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("88888888-8888-4888-8888-888888888888")
RUN_ID = uuid.UUID("99999999-9999-4999-8999-999999999999")

CONTEXT = (
    "Line one reached ninety two percent of planned production output. "
    "Line two was halted twice for preventive maintenance downtime."
)


def case(**overrides: object) -> AIEvaluationCase:
    params: dict = {
        "tenantId": TENANT,
        "suiteCode": "RAG_GOLDEN",
        "caseCode": "PRODUCTION_OUTPUT",
        "question": "what was the production output",
        "expectedTerms": ("ninety two percent",),
        "createdAt": CLOCK,
        "updatedAt": CLOCK,
    }
    params.update(overrides)
    return AIEvaluationCase(**params)


def observation(**overrides: object) -> CaseObservation:
    params: dict = {
        "answer": "Line one reached ninety two percent of planned production output.",
        "contextText": CONTEXT,
        "citationCount": 1,
    }
    params.update(overrides)
    return CaseObservation(**params)


class VocabularyTests(unittest.TestCase):
    def testClosedVocabulariesAreStable(self) -> None:
        self.assertIn("GROUNDEDNESS", EVALUATION_METRICS)
        self.assertIn("SAFETY", EVALUATION_METRICS)
        self.assertEqual(EVALUATION_VERDICTS, ("PASS", "WARN", "FAIL"))
        self.assertIn("COMPLETED", RUN_STATUSES)

    def testValuesAreNormalized(self) -> None:
        self.assertEqual(ensureMetric(" groundedness "), "GROUNDEDNESS")
        self.assertEqual(ensureVerdict("warn"), "WARN")
        with self.assertRaises(ValidationFailedError):
            ensureMetric("VIBES")
        with self.assertRaises(ValidationFailedError):
            ensureVerdict("MAYBE")

    def testCodesAreUppercaseIdentifiers(self) -> None:
        self.assertEqual(ensureCode(" rag golden "), "RAG_GOLDEN")
        for bad in ("", "1BAD", "x" * 200):
            with self.assertRaises(ValidationFailedError):
                ensureCode(bad)

    def testWorstVerdictCombines(self) -> None:
        self.assertEqual(worstVerdict(["PASS", "WARN", "FAIL"]), "FAIL")
        self.assertEqual(worstVerdict(["PASS", "WARN"]), "WARN")
        self.assertEqual(worstVerdict(["PASS", "PASS"]), "PASS")


class ScoringMathTests(unittest.TestCase):
    def testClampKeepsScoresInsideTheUnitInterval(self) -> None:
        self.assertEqual(clampScore(1.5), 1.0)
        self.assertEqual(clampScore(-2), 0.0)
        self.assertEqual(clampScore(0.4444444444), 0.444444)
        with self.assertRaises(ValidationFailedError):
            clampScore(float("nan"))
        with self.assertRaises(ValidationFailedError):
            clampScore("high")  # type: ignore[arg-type]

    def testCoverageCountsExpectedTerms(self) -> None:
        self.assertEqual(coverageScore(("alpha", "beta"), "alpha and beta appear"), 1.0)
        self.assertEqual(coverageScore(("alpha", "beta"), "only alpha appears"), 0.5)
        self.assertEqual(coverageScore((), "anything"), 1.0)
        self.assertEqual(coverageScore(("alpha",), ""), 0.0)

    def testCoverageMatchesMultiWordTerms(self) -> None:
        self.assertEqual(coverageScore(("ninety two percent",), CONTEXT), 1.0)
        self.assertEqual(coverageScore(("ninety nine percent",), CONTEXT), 0.0)

    def testGroundednessMeasuresSupportedTokens(self) -> None:
        self.assertGreater(groundednessScore("production output", CONTEXT), 0.9)
        self.assertEqual(groundednessScore("", CONTEXT), 0.0)
        self.assertEqual(groundednessScore("anything", ""), 0.0)
        self.assertLess(groundednessScore("unrelated invented statement", CONTEXT), 0.4)

    def testBudgetScoreRewardsStayingUnderBudget(self) -> None:
        self.assertEqual(budgetScore(500, 1000), 1.0)
        self.assertEqual(budgetScore(1000, 1000), 1.0)
        self.assertEqual(budgetScore(2000, 1000), 0.5)
        self.assertEqual(budgetScore(100, 0), 1.0)

    def testWeightedAverageHonoursWeights(self) -> None:
        scores = {"GROUNDEDNESS": 1.0, "RELEVANCE": 0.0}
        self.assertEqual(weightedAverage(scores, {}), 0.5)
        self.assertGreater(weightedAverage(scores, {"GROUNDEDNESS": 3.0, "RELEVANCE": 1.0}), 0.7)
        self.assertEqual(weightedAverage({}, {}), 0.0)
        with self.assertRaises(ValidationFailedError):
            weightedAverage(scores, {"GROUNDEDNESS": -1.0})


class CriteriaTests(unittest.TestCase):
    def testThresholdBandsProduceVerdicts(self) -> None:
        threshold = MetricThreshold(metric="RELEVANCE", failBelow=0.4, warnBelow=0.7)
        self.assertEqual(threshold.verdictFor(0.9), "PASS")
        self.assertEqual(threshold.verdictFor(0.5), "WARN")
        self.assertEqual(threshold.verdictFor(0.1), "FAIL")

    def testThresholdValidatesItsBands(self) -> None:
        with self.assertRaises(ValidationFailedError):
            MetricThreshold(metric="RELEVANCE", failBelow=0.9, warnBelow=0.5)
        with self.assertRaises(ValidationFailedError):
            MetricThreshold(metric="RELEVANCE", failBelow=1.5)
        with self.assertRaises(ValidationFailedError):
            MetricThreshold(metric="RELEVANCE", weight=-1)

    def testPlatformCriteriaMakeGroundednessAndSafetyRequired(self) -> None:
        criteria = EvaluationCriteria.platformDefault()
        self.assertIn("GROUNDEDNESS", criteria.requiredMetrics)
        self.assertIn("SAFETY", criteria.requiredMetrics)
        self.assertEqual(criteria.thresholdFor("SAFETY").failBelow, 1.0)

    def testUnknownMetricFallsBackToADefaultThreshold(self) -> None:
        criteria = EvaluationCriteria(thresholds=(MetricThreshold(metric="RELEVANCE"),))
        self.assertEqual(criteria.thresholdFor("COST").metric, "COST")

    def testDuplicateThresholdsAreRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            EvaluationCriteria(
                thresholds=(
                    MetricThreshold(metric="RELEVANCE"),
                    MetricThreshold(metric="RELEVANCE", failBelow=0.1),
                )
            )

    def testRunLevelLimitsAreValidated(self) -> None:
        with self.assertRaises(ValidationFailedError):
            EvaluationCriteria(minimumOverallScore=1.5)
        with self.assertRaises(ValidationFailedError):
            EvaluationCriteria(maximumFailedCases=-1)
        with self.assertRaises(ValidationFailedError):
            EvaluationCriteria(maximumWarnRatio=2.0)
        with self.assertRaises(ValidationFailedError):
            EvaluationCriteria(regressionTolerance=-0.1)

    def testSignatureIsStableAndOrderIndependent(self) -> None:
        first = EvaluationCriteria(
            thresholds=(
                MetricThreshold(metric="RELEVANCE"),
                MetricThreshold(metric="SAFETY", required=True),
            )
        )
        second = EvaluationCriteria(
            thresholds=(
                MetricThreshold(metric="SAFETY", required=True),
                MetricThreshold(metric="RELEVANCE"),
            )
        )
        self.assertEqual(first.signature(), second.signature())
        self.assertNotEqual(first.signature(), EvaluationCriteria().signature())

    def testMetricScoreEvaluatesAgainstItsThreshold(self) -> None:
        criteria = EvaluationCriteria.platformDefault()
        score = MetricScore.evaluate("GROUNDEDNESS", 0.6, criteria)
        self.assertEqual(score.verdict, "WARN")
        self.assertTrue(score.required)
        self.assertEqual(score.weight, 2.0)


class EntityTests(unittest.TestCase):
    def testCaseNormalizesAndValidates(self) -> None:
        item = case()
        self.assertEqual(item.qualifiedCode, "RAG_GOLDEN:PRODUCTION_OUTPUT")
        self.assertFalse(item.expectsStructuredOutput)
        with self.assertRaises(ValidationFailedError):
            case(question="   ")
        with self.assertRaises(ValidationFailedError):
            case(minimumCitations=-1)
        with self.assertRaises(ValidationFailedError):
            case(expectedSchema=["nope"])

    def testCaseLifecycle(self) -> None:
        item = case()
        item.deactivate(now=CLOCK)
        self.assertFalse(item.isActive)
        item.activate(now=CLOCK)
        self.assertTrue(item.isActive)

    def testRunLifecycleFollowsItsMachine(self) -> None:
        run = AIEvaluationRun(tenantId=TENANT, suiteCode="RAG_GOLDEN", createdAt=CLOCK)
        run.transitionTo("RUNNING", now=CLOCK)
        self.assertEqual(run.startedAt, CLOCK)
        run.complete(
            verdict="PASS", overallScore=0.9, passedCount=2, warnedCount=0, failedCount=0, now=CLOCK
        )
        self.assertEqual(run.status, "COMPLETED")
        self.assertEqual(run.caseCount, 2)
        self.assertEqual(run.passRate, 1.0)
        self.assertTrue(run.isTerminal)
        with self.assertRaises(ValidationFailedError):
            run.transitionTo("RUNNING", now=CLOCK)

    def testRunCanFailWithAStableCode(self) -> None:
        run = AIEvaluationRun(tenantId=TENANT, suiteCode="RAG_GOLDEN", createdAt=CLOCK)
        run.transitionTo("RUNNING", now=CLOCK)
        run.fail("ai_provider_unavailable", now=CLOCK)
        self.assertEqual(run.status, "FAILED")
        self.assertEqual(run.verdict, "FAIL")
        self.assertEqual(run.errorCode, "AI_PROVIDER_UNAVAILABLE")

    def testIllegalRunTransitionIsRejected(self) -> None:
        run = AIEvaluationRun(tenantId=TENANT, suiteCode="RAG_GOLDEN", createdAt=CLOCK)
        with self.assertRaises(ValidationFailedError):
            run.transitionTo("COMPLETED", now=CLOCK)

    def testResultExposesMetricsAndFailures(self) -> None:
        criteria = EvaluationCriteria.platformDefault()
        result = AIEvaluationResult(
            tenantId=TENANT,
            runId=RUN_ID,
            caseCode="PRODUCTION_OUTPUT",
            scores=(
                MetricScore.evaluate("GROUNDEDNESS", 0.95, criteria),
                MetricScore.evaluate("RELEVANCE", 0.1, criteria),
            ),
            createdAt=CLOCK,
        )
        result.recomputeVerdict(criteria)
        self.assertEqual(result.verdict, "FAIL")
        self.assertEqual(result.failedMetrics(), ("RELEVANCE",))
        self.assertIn("GROUNDEDNESS", result.metricMap())
        self.assertIsNone(result.scoreFor("COST"))

    def testResultFailsWhenARequiredMetricIsMissing(self) -> None:
        criteria = EvaluationCriteria.platformDefault()
        result = AIEvaluationResult(
            tenantId=TENANT,
            runId=RUN_ID,
            caseCode="X",
            scores=(MetricScore.evaluate("RELEVANCE", 1.0, criteria),),
            createdAt=CLOCK,
        )
        result.recomputeVerdict(criteria)
        self.assertEqual(result.verdict, "FAIL")

    def testResultBridgesToPhase13BEvaluation(self) -> None:
        criteria = EvaluationCriteria.platformDefault()
        requestId = uuid.uuid4()
        result = AIEvaluationResult(
            tenantId=TENANT,
            runId=RUN_ID,
            caseCode="X",
            scores=(MetricScore.evaluate("RELEVANCE", 0.8, criteria),),
            requestId=requestId,
            createdAt=CLOCK,
        )
        bridged = result.toDomainEvaluation()
        self.assertIsInstance(bridged, AIEvaluation)
        self.assertEqual(bridged.requestId, requestId)
        self.assertIn("RELEVANCE", bridged.metrics)

    def testBridgeRefusesWithoutARequestId(self) -> None:
        result = AIEvaluationResult(tenantId=TENANT, runId=RUN_ID, caseCode="X", createdAt=CLOCK)
        with self.assertRaises(ValidationFailedError):
            result.toDomainEvaluation()


class EngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = EvaluationEngine()
        self.criteria = EvaluationCriteria.platformDefault()

    def testGroundedAnswerScoresHigh(self) -> None:
        score, detail = self.engine.groundedness(observation())
        self.assertGreater(score, 0.9)
        self.assertIn("%", detail)

    def testInventedAnswerScoresLow(self) -> None:
        score, _ = self.engine.groundedness(
            observation(answer="Revenue tripled after the merger with Acme Corporation.")
        )
        self.assertLess(score, 0.5)

    def testMissingContextIsNeverGrounded(self) -> None:
        score, detail = self.engine.groundedness(observation(contextText=""))
        self.assertEqual(score, 0.0)
        self.assertIn("cannot be grounded", detail)

    def testRelevanceMeasuresQuestionCoverage(self) -> None:
        score, _ = self.engine.relevance(case(), observation())
        self.assertGreater(score, 0.5)
        low, _ = self.engine.relevance(case(), observation(answer="The weather is fine."))
        self.assertLess(low, score)

    def testCompletenessChecksExpectedTerms(self) -> None:
        score, _ = self.engine.completeness(case(), observation())
        self.assertEqual(score, 1.0)
        missing, _ = self.engine.completeness(
            case(expectedTerms=("eighty percent",)), observation()
        )
        self.assertEqual(missing, 0.0)

    def testCitationCoverageComparesAgainstTheMinimum(self) -> None:
        full, _ = self.engine.citationCoverage(case(minimumCitations=1), observation())
        self.assertEqual(full, 1.0)
        half, _ = self.engine.citationCoverage(
            case(minimumCitations=2), observation(citationCount=1)
        )
        self.assertEqual(half, 0.5)
        none, detail = self.engine.citationCoverage(case(), observation(citationCount=0))
        self.assertEqual(none, 1.0)
        self.assertIn("No citation minimum", detail)

    def testSchemaValidityIsBinary(self) -> None:
        schema = {"type": "object", "required": ["value"]}
        good, _ = self.engine.schemaValidity(
            case(expectedSchema=schema), observation(structuredData={"value": 1})
        )
        self.assertEqual(good, 1.0)
        bad, _ = self.engine.schemaValidity(
            case(expectedSchema=schema), observation(structuredData={"other": 1})
        )
        self.assertEqual(bad, 0.0)
        missing, detail = self.engine.schemaValidity(case(expectedSchema=schema), observation())
        self.assertEqual(missing, 0.0)
        self.assertIn("not produced", detail)

    def testSafetyFailsOnAForbiddenTerm(self) -> None:
        score, detail = self.engine.safety(
            case(forbiddenTerms=("password",)),
            observation(answer="The PASSWORD is hunter2."),
        )
        self.assertEqual(score, 0.0)
        self.assertIn("password", detail)

    def testPlatformWideForbiddenTermsAlsoApply(self) -> None:
        engine = EvaluationEngine(forbiddenTerms=("api key",))
        score, _ = engine.safety(case(), observation(answer="Here is the API key: abc."))
        self.assertEqual(score, 0.0)

    def testLatencyAndCostScoreAgainstBudgets(self) -> None:
        latency, _ = self.engine.latency(case(latencyBudgetMs=1000), observation(latencyMs=500))
        self.assertEqual(latency, 1.0)
        slow, _ = self.engine.latency(case(latencyBudgetMs=1000), observation(latencyMs=4000))
        self.assertEqual(slow, 0.25)
        cost, _ = self.engine.cost(case(costBudget="0.10"), observation(cost="0.20"))
        self.assertEqual(cost, 0.5)
        free, detail = self.engine.cost(case(), observation(cost="5"))
        self.assertEqual(free, 1.0)
        self.assertIn("No cost budget", detail)

    def testScoreCaseComputesEveryCriteriaMetric(self) -> None:
        scores = self.engine.scoreCase(case(), observation(), self.criteria)
        self.assertEqual({item.metric for item in scores}, set(self.criteria.metrics))

    def testScoreCaseCanBeNarrowedToSpecificMetrics(self) -> None:
        scores = self.engine.scoreCase(
            case(), observation(), self.criteria, metrics=("GROUNDEDNESS",)
        )
        self.assertEqual([item.metric for item in scores], ["GROUNDEDNESS"])

    def testScoringIsDeterministic(self) -> None:
        first = self.engine.scoreCase(case(), observation(), self.criteria)
        second = self.engine.scoreCase(case(), observation(), self.criteria)
        self.assertEqual(
            [(item.metric, item.score) for item in first],
            [(item.metric, item.score) for item in second],
        )

    def testForeignInputIsRejected(self) -> None:
        with self.assertRaises(AIEvaluationInvalid):
            self.engine.scoreCase("case", observation(), self.criteria)  # type: ignore[arg-type]
        with self.assertRaises(AIEvaluationInvalid):
            self.engine.scoreCase(case(), "observation", self.criteria)  # type: ignore[arg-type]
        with self.assertRaises(AIEvaluationCriteriaInvalid):
            self.engine.scoreCase(case(), observation(), "criteria")  # type: ignore[arg-type]

    def testObservationValidatesItsMeasurements(self) -> None:
        with self.assertRaises(AIEvaluationInvalid):
            CaseObservation(answer="a", latencyMs=-1)
        with self.assertRaises(AIEvaluationInvalid):
            CaseObservation(answer=None)  # type: ignore[arg-type]
        self.assertTrue(CaseObservation(answer="", errorCode="boom").failed)


class JudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.judge = EvaluationJudge()
        self.criteria = EvaluationCriteria.platformDefault()

    def scores(self, **values: float) -> tuple[MetricScore, ...]:
        return tuple(
            MetricScore.evaluate(metric, score, self.criteria) for metric, score in values.items()
        )

    def testAllGoodMetricsPass(self) -> None:
        verdict = self.judge.judge(
            self.scores(GROUNDEDNESS=0.95, RELEVANCE=0.9, SAFETY=1.0), self.criteria
        )
        self.assertEqual(verdict.verdict, "PASS")
        self.assertEqual(verdict.failedMetrics, ())

    def testOneFailingMetricFailsTheCase(self) -> None:
        verdict = self.judge.judge(
            self.scores(GROUNDEDNESS=0.2, RELEVANCE=0.9, SAFETY=1.0), self.criteria
        )
        self.assertEqual(verdict.verdict, "FAIL")
        self.assertEqual(verdict.failedMetrics, ("GROUNDEDNESS",))
        self.assertIn("GROUNDEDNESS", verdict.reason)

    def testAWarningMetricWarnsTheCase(self) -> None:
        verdict = self.judge.judge(
            self.scores(GROUNDEDNESS=0.6, RELEVANCE=0.9, SAFETY=1.0), self.criteria
        )
        self.assertEqual(verdict.verdict, "WARN")

    def testMissingRequiredMetricFails(self) -> None:
        verdict = self.judge.judge(self.scores(RELEVANCE=1.0), self.criteria)
        self.assertEqual(verdict.verdict, "FAIL")
        self.assertIn("SAFETY", verdict.missingMetrics)

    def testLowOverallScoreDowngradesToWarn(self) -> None:
        criteria = EvaluationCriteria(
            thresholds=(MetricThreshold(metric="RELEVANCE", failBelow=0.0, warnBelow=0.0),),
            minimumOverallScore=0.9,
        )
        verdict = self.judge.judge((MetricScore.evaluate("RELEVANCE", 0.5, criteria),), criteria)
        self.assertEqual(verdict.verdict, "WARN")

    def testNoScoresIsAFailure(self) -> None:
        verdict = self.judge.judge((), self.criteria)
        self.assertEqual(verdict.verdict, "FAIL")
        self.assertEqual(verdict.score, 0.0)

    def testForeignCriteriaAreRejected(self) -> None:
        with self.assertRaises(AIEvaluationCriteriaInvalid):
            self.judge.judge((), "criteria")  # type: ignore[arg-type]


class AggregatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aggregator = RunAggregator()
        self.criteria = EvaluationCriteria.platformDefault()

    def result(self, code: str, verdict: str, score: float) -> AIEvaluationResult:
        return AIEvaluationResult(
            tenantId=TENANT,
            runId=RUN_ID,
            caseCode=code,
            verdict=verdict,
            score=score,
            scores=(MetricScore.evaluate("GROUNDEDNESS", score, self.criteria),),
            createdAt=CLOCK,
        )

    def testAllPassingCasesPassTheRun(self) -> None:
        summary = self.aggregator.aggregate(
            [self.result("A", "PASS", 0.9), self.result("B", "PASS", 0.95)], self.criteria
        )
        self.assertEqual(summary.verdict, "PASS")
        self.assertEqual(summary.passRate, 1.0)
        self.assertIn("GROUNDEDNESS", summary.metricAverages)

    def testOneFailingCaseFailsTheRunUnderTheDefaultBar(self) -> None:
        summary = self.aggregator.aggregate(
            [self.result("A", "PASS", 0.9), self.result("B", "FAIL", 0.1)], self.criteria
        )
        self.assertEqual(summary.verdict, "FAIL")
        self.assertIn("failed", summary.reason)

    def testFailuresAreToleratedWhenTheBarAllowsIt(self) -> None:
        criteria = EvaluationCriteria(
            thresholds=self.criteria.thresholds,
            minimumOverallScore=0.4,
            maximumFailedCases=1,
        )
        summary = self.aggregator.aggregate(
            [self.result("A", "PASS", 0.9), self.result("B", "FAIL", 0.1)], criteria
        )
        self.assertNotEqual(summary.verdict, "FAIL")

    def testTooManyWarningsDowngradeTheRun(self) -> None:
        criteria = EvaluationCriteria(
            thresholds=self.criteria.thresholds,
            minimumOverallScore=0.5,
            maximumWarnRatio=0.1,
        )
        summary = self.aggregator.aggregate(
            [self.result("A", "WARN", 0.7), self.result("B", "PASS", 0.9)], criteria
        )
        self.assertEqual(summary.verdict, "WARN")
        self.assertGreater(summary.warnRatio, 0.1)

    def testLowAverageFailsEvenWithoutFailingCases(self) -> None:
        summary = self.aggregator.aggregate(
            [self.result("A", "WARN", 0.5), self.result("B", "WARN", 0.55)], self.criteria
        )
        self.assertEqual(summary.verdict, "FAIL")
        self.assertIn("below the minimum", summary.reason)

    def testEmptyRunIsAFailure(self) -> None:
        summary = self.aggregator.aggregate([], self.criteria)
        self.assertEqual(summary.verdict, "FAIL")
        self.assertEqual(summary.caseCount, 0)
        self.assertEqual(summary.passRate, 0.0)


class RegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.criteria = EvaluationCriteria.platformDefault()

    def summary(self, score: float, **metrics: float) -> RunSummary:
        return RunSummary(
            verdict="PASS",
            overallScore=score,
            caseCount=2,
            passedCount=2,
            warnedCount=0,
            failedCount=0,
            metricAverages=dict(metrics),
        )

    def testFlatRunIsNotARegression(self) -> None:
        report = compareRuns(self.summary(0.9), self.summary(0.9), self.criteria)
        self.assertFalse(report.regressed)
        self.assertEqual(report.overallDelta, 0.0)

    def testSmallDropInsideToleranceIsNotARegression(self) -> None:
        report = compareRuns(self.summary(0.90), self.summary(0.89), self.criteria)
        self.assertFalse(report.regressed)

    def testLargerDropIsARegression(self) -> None:
        report = compareRuns(self.summary(0.90), self.summary(0.70), self.criteria)
        self.assertTrue(report.regressed)
        self.assertLess(report.overallDelta, 0)
        self.assertIn("dropped", report.reason)

    def testMetricRegressionIsDetectedEvenWhenTheAverageHolds(self) -> None:
        report = compareRuns(
            self.summary(0.9, GROUNDEDNESS=0.95, COST=0.5),
            self.summary(0.9, GROUNDEDNESS=0.60, COST=0.9),
            self.criteria,
        )
        self.assertTrue(report.regressed)
        self.assertIn("GROUNDEDNESS", report.regressedMetrics)

    def testNewFailingCaseIsAlwaysARegression(self) -> None:
        report = compareRuns(
            self.summary(0.9),
            self.summary(0.95),
            self.criteria,
            baselineFailures=(),
            candidateFailures=("CASE_B",),
        )
        self.assertTrue(report.regressed)
        self.assertEqual(report.newFailures, ("CASE_B",))

    def testFixedFailuresAreReported(self) -> None:
        report = compareRuns(
            self.summary(0.8),
            self.summary(0.9),
            self.criteria,
            baselineFailures=("CASE_A",),
            candidateFailures=(),
        )
        self.assertFalse(report.regressed)
        self.assertEqual(report.fixedFailures, ("CASE_A",))

    def testImprovementIsReportedPerMetric(self) -> None:
        report = compareRuns(
            self.summary(0.8, RELEVANCE=0.5), self.summary(0.9, RELEVANCE=0.8), self.criteria
        )
        delta = next(item for item in report.metricDeltas if item.metric == "RELEVANCE")
        self.assertTrue(delta.improved)
        self.assertGreater(delta.delta, 0)

    def testForeignCriteriaAreRejected(self) -> None:
        with self.assertRaises(AIEvaluationCriteriaInvalid):
            compareRuns(self.summary(0.9), self.summary(0.9), "criteria")  # type: ignore[arg-type]


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
