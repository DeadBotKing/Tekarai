"""Phase 13-U application tests — evaluation over a real SQLite database.

Covers golden-case administration, a full suite run with scoring and
judging, the per-case failure isolation that keeps one broken case from
killing a run, the aggregate verdict under configurable criteria,
regression detection against the previous run, retention, tenant
isolation, the fail-closed switch, the Phase 13-O audit trail, and the
Phase 13-P ``EVALUATION`` job.

The final class grades the **real Phase 13-S RAG pipeline** (with real
Q embeddings, real R chunks, and the real K permission filter) through the
same suite machinery, which is the point of U: the quality bar is applied
to the actual product, not to a mock.
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
)
from apps.ai.application.services.evaluationService import (
    AUDIT_EVALUATION_COMPLETED,
    AUDIT_EVALUATION_FAILED,
    AUDIT_EVALUATION_REGRESSED,
    AUDIT_EVALUATION_STARTED,
    EvaluationApplicationService,
    EvaluationJobHandler,
    EvaluationSettings,
    RegisterCaseCommand,
    RunSuiteCommand,
    observationFromRagAnswer,
)
from apps.ai.application.services.knowledgeService import (
    IngestKnowledgeCommand,
    KnowledgeApplicationService,
    KnowledgeSettings,
)
from apps.ai.application.services.queueService import (
    QueueApplicationService,
    QueueSettings,
    SubmitJobCommand,
)
from apps.ai.application.services.retrievalService import (
    RagRequest,
    RetrievalApplicationService,
    RetrievalSettings,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIEvaluationCaseAlreadyRegistered,
    AIEvaluationCaseNotFound,
    AIEvaluationCriteriaInvalid,
    AIEvaluationInvalid,
    AIEvaluationRunNotFound,
)
from apps.ai.domain.services.authorizationService import (
    AuthorizationPrincipal,
    AuthorizationService,
    PermissionGrant,
)
from apps.ai.domain.services.evaluationEngine import CaseObservation
from apps.ai.domain.valueObjects.evaluationTypes import (
    EvaluationCriteria,
    MetricThreshold,
)
from apps.ai.infrastructure.models import AIEvaluationRunModel
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)
from apps.ai.infrastructure.repositories.embeddingRepositories import (
    DjangoEmbeddingStore,
    DjangoVectorSpaceStore,
)
from apps.ai.infrastructure.repositories.evaluationRepositories import (
    DjangoEvaluationCaseStore,
    DjangoEvaluationRunStore,
)
from apps.ai.infrastructure.repositories.knowledgeRepositories import (
    DjangoKnowledgeChunkStore,
    DjangoKnowledgeSourceStore,
)
from apps.ai.infrastructure.repositories.queueRepositories import DjangoJobStore
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)

CONTEXT = (
    "Line one reached ninety two percent of planned production output. "
    "Line two was halted twice for preventive maintenance downtime."
)


class ScriptedProducer:
    """Answer producer double: per-case scripted observations."""

    def __init__(self, answers: dict[str, CaseObservation] | None = None) -> None:
        self.answers = answers or {}
        self.default = CaseObservation(
            answer="Line one reached ninety two percent of planned production output.",
            contextText=CONTEXT,
            citationCount=1,
            latencyMs=100,
            totalTokens=40,
            cost="0.001",
        )
        self.calls: list[str] = []
        self.raiseFor: set[str] = set()

    def produce(self, tenantId: Any, case: Any) -> CaseObservation:
        self.calls.append(case.caseCode)
        if case.caseCode in self.raiseFor:
            raise RuntimeError("producer exploded")
        return self.answers.get(case.caseCode, self.default)


class EvaluationTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.clock = CLOCK
        self.caseStore = DjangoEvaluationCaseStore()
        self.runStore = DjangoEvaluationRunStore()
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=AuditSettings(enabled=True, retentionDays=365),
            now=lambda: CLOCK,
        )
        self.producer = ScriptedProducer()
        self.service = self.buildService()

    def buildService(self, **overrides: Any) -> EvaluationApplicationService:
        settings = EvaluationSettings(
            enabled=overrides.pop("enabled", True),
            minimumOverallScore=overrides.pop("minimumOverallScore", 0.6),
            maximumFailedCases=overrides.pop("maximumFailedCases", 0),
            maximumWarnRatio=overrides.pop("maximumWarnRatio", 0.5),
            regressionTolerance=overrides.pop("regressionTolerance", 0.02),
            maxCasesPerRun=overrides.pop("maxCasesPerRun", 200),
            retentionDays=overrides.pop("retentionDays", 365),
            forbiddenTerms=overrides.pop("forbiddenTerms", ()),
        )
        return EvaluationApplicationService(
            self.caseStore,
            self.runStore,
            producer=overrides.pop("producer", self.producer),
            settings=settings,
            auditLogger=overrides.pop("auditLogger", self.audit),
            now=lambda: self.clock,
        )

    def registerCase(self, caseCode: str = "PRODUCTION_OUTPUT", **overrides: Any) -> Any:
        params: dict[str, Any] = {
            "suiteCode": "RAG_GOLDEN",
            "caseCode": caseCode,
            "question": "what was the production output",
            "expectedTerms": ("ninety two percent",),
            "minimumCitations": 1,
        }
        params.update(overrides)
        return self.service.registerCase(self.tenantId, RegisterCaseCommand(**params))

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class GoldenCaseTests(EvaluationTestCase):
    def testRegisteringACasePersistsIt(self) -> None:
        descriptor = self.registerCase()
        self.assertEqual(descriptor.qualifiedCode, "RAG_GOLDEN:PRODUCTION_OUTPUT")
        self.assertTrue(descriptor.isActive)
        self.assertEqual(self.service.listSuites(self.tenantId), ("RAG_GOLDEN",))

    def testDuplicateCaseIsRejectedUnlessReplacing(self) -> None:
        self.registerCase()
        with self.assertRaises(AIEvaluationCaseAlreadyRegistered):
            self.registerCase()
        replaced = self.registerCase(question="updated question", replace=True)
        self.assertEqual(replaced.question, "updated question")
        self.assertEqual(len(self.service.listCases(self.tenantId)), 1)

    def testCasesAreListedAndFilteredBySuite(self) -> None:
        self.registerCase("A")
        self.registerCase("B", suiteCode="SAFETY_GOLDEN")
        self.assertEqual(len(self.service.listCases(self.tenantId)), 2)
        self.assertEqual(len(self.service.listCases(self.tenantId, "SAFETY_GOLDEN")), 1)
        self.assertEqual(self.service.listSuites(self.tenantId), ("RAG_GOLDEN", "SAFETY_GOLDEN"))

    def testDeactivatedCaseLeavesTheActiveList(self) -> None:
        self.registerCase()
        self.service.deactivateCase(self.tenantId, "RAG_GOLDEN", "PRODUCTION_OUTPUT")
        self.assertEqual(self.service.listCases(self.tenantId), ())
        self.assertEqual(len(self.service.listCases(self.tenantId, activeOnly=False)), 1)

    def testUnknownCaseIsNotFound(self) -> None:
        with self.assertRaises(AIEvaluationCaseNotFound):
            self.service.describeCase(self.tenantId, "RAG_GOLDEN", "MISSING")
        with self.assertRaises(AIEvaluationCaseNotFound):
            self.service.deactivateCase(self.tenantId, "RAG_GOLDEN", "MISSING")

    def testCasesAreTenantScoped(self) -> None:
        self.registerCase()
        self.assertEqual(self.service.listCases(self.otherTenantId), ())
        with self.assertRaises(AIEvaluationCaseNotFound):
            self.service.describeCase(self.otherTenantId, "RAG_GOLDEN", "PRODUCTION_OUTPUT")

    def testInvalidCommandsAreRejected(self) -> None:
        with self.assertRaises(AIEvaluationInvalid):
            self.service.registerCase(self.tenantId, "case")  # type: ignore[arg-type]
        with self.assertRaises(ValidationFailedError):
            self.registerCase(question="   ")

    def testDisabledPlatformRefusesEverything(self) -> None:
        disabled = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            disabled.listCases(self.tenantId)
        with self.assertRaises(AIConfigurationError):
            disabled.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))


class RunTests(EvaluationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.registerCase()

    def testAGoodAnswerPassesTheSuite(self) -> None:
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertEqual(report.run.status, "COMPLETED")
        self.assertEqual(report.run.verdict, "PASS")
        self.assertEqual(report.summary.passedCount, 1)
        self.assertTrue(report.accepted)
        self.assertIn(AUDIT_EVALUATION_STARTED, self.auditActions())
        self.assertIn(AUDIT_EVALUATION_COMPLETED, self.auditActions())

    def testAnUngroundedAnswerFailsTheSuite(self) -> None:
        self.producer.answers["PRODUCTION_OUTPUT"] = CaseObservation(
            answer="Revenue tripled after the merger with Acme Corporation.",
            contextText=CONTEXT,
            citationCount=1,
        )
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertEqual(report.run.verdict, "FAIL")
        self.assertFalse(report.accepted)
        self.assertIn("GROUNDEDNESS", report.results[0].failedMetrics)

    def testAForbiddenTermFailsOnSafety(self) -> None:
        self.registerCase(
            "SECRET_LEAK",
            forbiddenTerms=("password",),
            expectedTerms=(),
            minimumCitations=0,
        )
        self.producer.answers["SECRET_LEAK"] = CaseObservation(
            answer="The production password is hunter2.", contextText=CONTEXT
        )
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        leak = next(item for item in report.results if item.caseCode == "SECRET_LEAK")
        self.assertEqual(leak.verdict, "FAIL")
        self.assertIn("SAFETY", leak.failedMetrics)

    def testMissingCitationsDowngradeTheCase(self) -> None:
        self.producer.answers["PRODUCTION_OUTPUT"] = CaseObservation(
            answer="Line one reached ninety two percent of planned production output.",
            contextText=CONTEXT,
            citationCount=0,
        )
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        result = report.results[0]
        self.assertEqual(result.metrics["CITATION_COVERAGE"], 0.0)
        self.assertEqual(result.verdict, "FAIL")

    def testABrokenCaseFailsThatCaseNotTheRun(self) -> None:
        self.registerCase("SECOND_CASE")
        self.producer.raiseFor.add("SECOND_CASE")
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertEqual(report.run.status, "COMPLETED")
        self.assertEqual(report.summary.caseCount, 2)
        broken = next(item for item in report.results if item.caseCode == "SECOND_CASE")
        self.assertEqual(broken.verdict, "FAIL")
        self.assertEqual(broken.errorCode, "AI_EVALUATION_FAILED")

    def testASubjectReportedErrorFailsTheCase(self) -> None:
        self.producer.answers["PRODUCTION_OUTPUT"] = CaseObservation(
            answer="", errorCode="AI_RAG_UNGROUNDED", latencyMs=12
        )
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertEqual(report.results[0].errorCode, "AI_RAG_UNGROUNDED")
        self.assertEqual(report.run.verdict, "FAIL")

    def testRunCanBeNarrowedToSpecificCases(self) -> None:
        self.registerCase("SECOND_CASE")
        report = self.service.runSuite(
            self.tenantId,
            RunSuiteCommand(suiteCode="RAG_GOLDEN", caseCodes=("PRODUCTION_OUTPUT",)),
        )
        self.assertEqual(report.summary.caseCount, 1)
        self.assertEqual(self.producer.calls, ["PRODUCTION_OUTPUT"])

    def testMetricsCanBeNarrowedForAFastRun(self) -> None:
        report = self.service.runSuite(
            self.tenantId,
            RunSuiteCommand(suiteCode="RAG_GOLDEN", metrics=("GROUNDEDNESS", "SAFETY")),
        )
        self.assertEqual(set(report.results[0].metrics), {"GROUNDEDNESS", "SAFETY"})

    def testCustomCriteriaChangeTheVerdict(self) -> None:
        self.producer.answers["PRODUCTION_OUTPUT"] = CaseObservation(
            answer="Production output was reported.", contextText=CONTEXT, citationCount=1
        )
        strict = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        lenient = self.service.runSuite(
            self.tenantId,
            RunSuiteCommand(
                suiteCode="RAG_GOLDEN",
                criteria=EvaluationCriteria(
                    thresholds=(
                        MetricThreshold(
                            metric="GROUNDEDNESS", failBelow=0.1, warnBelow=0.2, required=True
                        ),
                        MetricThreshold(
                            metric="SAFETY", failBelow=1.0, warnBelow=1.0, required=True
                        ),
                    ),
                    minimumOverallScore=0.3,
                    maximumWarnRatio=1.0,
                ),
                compareToPrevious=False,
            ),
        )
        self.assertNotEqual(strict.run.verdict, lenient.run.verdict)

    def testTheCriteriaSignatureIsStampedOnTheRun(self) -> None:
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertIn("GROUNDEDNESS", report.run.criteriaSignature)

    def testRunningAnEmptySuiteIsRefused(self) -> None:
        with self.assertRaises(AIEvaluationInvalid):
            self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="EMPTY_SUITE"))

    def testMissingProducerFailsClosed(self) -> None:
        service = self.buildService(producer=None)
        with self.assertRaises(AIConfigurationError):
            service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))

    def testRunCeilingIsEnforced(self) -> None:
        service = self.buildService(maxCasesPerRun=1)
        self.registerCase("SECOND_CASE")
        with self.assertRaises(AIEvaluationInvalid):
            service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))

    def testAProducerReturningGarbageFailsTheRunLoudly(self) -> None:
        class BadProducer:
            def produce(self, tenantId: Any, case: Any) -> str:
                return "not an observation"

        service = self.buildService(producer=BadProducer())
        with self.assertRaises(AIEvaluationInvalid):
            service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        run = AIEvaluationRunModel.objects.order_by("-createdAt").first()
        assert run is not None
        self.assertEqual(run.status, "FAILED")
        self.assertIn(AUDIT_EVALUATION_FAILED, self.auditActions())


class RegressionTests(EvaluationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.registerCase()
        self.registerCase(
            "SECOND_CASE",
            question="why was line two halted for maintenance downtime",
            expectedTerms=("maintenance downtime",),
        )
        self.producer.answers["SECOND_CASE"] = CaseObservation(
            answer="Line two was halted twice for preventive maintenance downtime.",
            contextText=CONTEXT,
            citationCount=1,
        )

    def testAStableSecondRunReportsNoRegression(self) -> None:
        self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.clock = CLOCK + timedelta(minutes=5)
        second = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertIsNotNone(second.regression)
        assert second.regression is not None
        self.assertFalse(second.regression.regressed)
        self.assertTrue(second.accepted)

    def testADegradedSecondRunIsFlaggedAsARegression(self) -> None:
        self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.producer.answers["SECOND_CASE"] = CaseObservation(
            answer="Unrelated invented statement about quarterly revenue.",
            contextText=CONTEXT,
            citationCount=1,
        )
        self.clock = CLOCK + timedelta(minutes=5)
        second = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        assert second.regression is not None
        self.assertTrue(second.regression.regressed)
        self.assertIn("SECOND_CASE", second.regression.newFailures)
        self.assertFalse(second.accepted)
        self.assertIn(AUDIT_EVALUATION_REGRESSED, self.auditActions())

    def testTheFirstRunHasNoBaseline(self) -> None:
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertIsNone(report.regression)

    def testComparisonCanBeDisabled(self) -> None:
        self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.clock = CLOCK + timedelta(minutes=5)
        second = self.service.runSuite(
            self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN", compareToPrevious=False)
        )
        self.assertIsNone(second.regression)

    def testAnExplicitBaselineCanBeChosen(self) -> None:
        first = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.clock = CLOCK + timedelta(minutes=5)
        second = self.service.runSuite(
            self.tenantId,
            RunSuiteCommand(suiteCode="RAG_GOLDEN", baselineRunId=first.run.runId),
        )
        self.assertIsNotNone(second.regression)
        self.assertEqual(second.run.baselineRunId, first.run.runId)

    def testTwoSettledRunsCanBeComparedAfterwards(self) -> None:
        first = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.clock = CLOCK + timedelta(minutes=5)
        second = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        report = self.service.compareRunPair(self.tenantId, first.run.runId, second.run.runId)
        self.assertFalse(report.regressed)
        self.assertEqual(report.overallDelta, 0.0)

    def testRunsGradedUnderDifferentCriteriaCannotBeCompared(self) -> None:
        first = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.clock = CLOCK + timedelta(minutes=5)
        second = self.service.runSuite(
            self.tenantId,
            RunSuiteCommand(
                suiteCode="RAG_GOLDEN",
                criteria=EvaluationCriteria(
                    thresholds=(MetricThreshold(metric="SAFETY", required=True),),
                    minimumOverallScore=0.1,
                ),
                compareToPrevious=False,
            ),
        )
        with self.assertRaises(AIEvaluationCriteriaInvalid):
            self.service.compareRunPair(self.tenantId, first.run.runId, second.run.runId)


class RunReadTests(EvaluationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.registerCase()
        self.report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))

    def testRunsAndResultsAreReadable(self) -> None:
        described = self.service.describeRun(self.tenantId, self.report.run.runId)
        self.assertEqual(described.suiteCode, "RAG_GOLDEN")
        results = self.service.listResults(self.tenantId, self.report.run.runId)
        self.assertEqual(len(results), 1)
        self.assertIn("GROUNDEDNESS", results[0].metrics)

    def testRunsAreListedNewestFirst(self) -> None:
        self.clock = CLOCK + timedelta(minutes=5)
        self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        runs = self.service.listRuns(self.tenantId, "RAG_GOLDEN")
        self.assertEqual(len(runs), 2)
        self.assertGreaterEqual(runs[0].completedAt or CLOCK, runs[1].completedAt or CLOCK)

    def testRunsAreTenantScoped(self) -> None:
        self.assertEqual(self.service.listRuns(self.otherTenantId), ())
        with self.assertRaises(AIEvaluationRunNotFound):
            self.service.describeRun(self.otherTenantId, self.report.run.runId)

    def testRetentionPurgesSettledRunsOnly(self) -> None:
        self.assertEqual(self.service.purgeEvaluationRetention(self.tenantId, retentionDays=1), 0)
        future = CLOCK + timedelta(days=800)
        self.assertEqual(self.service.purgeEvaluationRetention(self.tenantId, now=future), 1)
        self.assertEqual(AIEvaluationRunModel.objects.count(), 0)

    def testRetentionRejectsAnImpossibleHorizon(self) -> None:
        with self.assertRaises(AIConfigurationError):
            self.service.purgeEvaluationRetention(self.tenantId, retentionDays=0)

    def testAuditChainStaysVerifiable(self) -> None:
        actions = self.auditActions()
        self.assertIn(AUDIT_EVALUATION_COMPLETED, actions)
        self.assertEqual(self.audit.verifyTenantChain(self.tenantId), len(actions))


class EvaluationJobTests(EvaluationTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.registerCase()
        self.queue = QueueApplicationService(
            DjangoJobStore(),
            auditService=self.audit,
            queueSettings=QueueSettings(enabled=True, defaultMaxAttempts=2, claimLimit=5),
            workerId="testWorker",
            now=lambda: CLOCK,
        )
        self.queue.registerHandler(EvaluationJobHandler(self.service))

    def testBatchEvaluationRunsThroughTheQueue(self) -> None:
        descriptor = self.queue.submitJob(
            SubmitJobCommand(
                tenantId=self.tenantId,
                kind="EVALUATION",
                payload={"suiteCode": "RAG_GOLDEN", "method": "BATCH"},
            )
        )
        report = self.queue.runOnce()
        self.assertEqual(report.succeeded, 1)
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "SUCCEEDED")
        self.assertEqual(settled.resultSummary["verdict"], "PASS")
        self.assertEqual(settled.resultSummary["passed"], 1)
        self.assertFalse(settled.resultSummary["regressed"])

    def testInvalidPayloadFailsTheJobNotTheWorker(self) -> None:
        descriptor = self.queue.submitJob(
            SubmitJobCommand(tenantId=self.tenantId, kind="EVALUATION", payload={"method": "BATCH"})
        )
        self.queue.runOnce()
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.errorCode, "AI_EVALUATION_INVALID")

    def testHandlerAdvertisesItsKind(self) -> None:
        self.assertEqual(EvaluationJobHandler(self.service).kind(), "EVALUATION")


class GradingTheRealPipelineTests(EvaluationTestCase):
    """U grading the actual Phase 13-S RAG pipeline, not a mock."""

    def setUp(self) -> None:
        super().setUp()
        vocabulary = ("production", "maintenance", "output", "downtime", "safety", "quality")

        class BagOfWordsProvider:
            def embed(self, *, text: str, model: str, **kwargs: Any) -> list[float]:
                lowered = text.lower()
                vector = [float(lowered.count(word)) for word in vocabulary]
                if not any(vector):
                    vector[0] = 0.001
                return vector

            def embedBatch(self, *, texts: Any, model: str, **kwargs: Any) -> list[list[float]]:
                return [self.embed(text=text, model=model) for text in texts]

        class FixedResolver:
            def __init__(self) -> None:
                self.provider = BagOfWordsProvider()

            def providerFor(self, tenantId: uuid.UUID, space: Any) -> BagOfWordsProvider:
                return self.provider

        class ContextEchoGenerator:
            """Answers by quoting the evidence — grounded by construction."""

            def generate(self, *, prompt: str, model: str, **kwargs: Any) -> str:
                body = prompt.split("Context:", 1)[-1].split("Question:", 1)[0]
                return " ".join(body.split())[:400]

        spaceStore = DjangoVectorSpaceStore()
        self.embedding = EmbeddingApplicationService(
            spaceStore,
            DjangoEmbeddingStore(spaceStore),
            providerResolver=FixedResolver(),
            settings=EmbeddingSettings(maxBatchSize=8, searchCandidateLimit=100),
            now=lambda: CLOCK,
        )
        self.embedding.defineVectorSpace(
            self.tenantId,
            DefineVectorSpaceCommand(
                code="KNOWLEDGE_SPACE",
                modelCode="TEXT_EMBED_3",
                dimensions=len(vocabulary),
                providerCode="LOCAL",
            ),
        )
        self.knowledge = KnowledgeApplicationService(
            DjangoKnowledgeSourceStore(),
            DjangoKnowledgeChunkStore(),
            embedder=self.embedding,
            settings=KnowledgeSettings(
                strategy="PARAGRAPH", chunkTokens=40, overlapTokens=0, minChunkTokens=0
            ),
            now=lambda: CLOCK,
        )
        self.knowledge.ingestSource(
            self.tenantId,
            IngestKnowledgeCommand(
                sourceDomain="DOCUMENTS",
                sourceEntityType="DOCUMENT",
                sourceEntityId="production",
                title="Production report",
                content=(
                    "Line one reached ninety two percent of planned production output.\n\n"
                    "Line two was halted twice for preventive maintenance downtime."
                ),
                spaceCode="KNOWLEDGE_SPACE",
            ),
        )
        authorization = AuthorizationService(now=lambda: CLOCK)
        subjectId = uuid.uuid4()
        self.principal = AuthorizationPrincipal(tenantId=self.tenantId, subjectId=subjectId)
        authorization.registerGrant(
            PermissionGrant(
                tenantId=self.tenantId,
                subjectId=subjectId,
                permissionCode="AI_CONTEXT_SOURCE_READ",
                resourceType="CONTEXT_SOURCE",
                allowedClassifications=("PUBLIC", "INTERNAL"),
            )
        )
        self.retrieval = RetrievalApplicationService(
            self.embedding,
            self.knowledge,
            permissionFilter=authorization,
            generator=ContextEchoGenerator(),
            settings=RetrievalSettings(topK=2, candidateLimit=20, maxContextTokens=2000),
            now=lambda: CLOCK,
        )

        outer = self

        class RagProducer:
            def produce(self, tenantId: Any, case: Any) -> CaseObservation:
                answer = outer.retrieval.answerQuestion(
                    tenantId,
                    RagRequest(
                        spaceCode=case.spaceCode or "KNOWLEDGE_SPACE",
                        question=case.question,
                        principal=outer.principal,
                        modelCode="TEST_MODEL",
                    ),
                )
                return observationFromRagAnswer(answer, latencyMs=25, cost="0.0005")

        self.service = self.buildService(producer=RagProducer())

    def testTheRealPipelinePassesItsGoldenSuite(self) -> None:
        self.registerCase(
            "PRODUCTION_OUTPUT",
            question="what was the production output",
            expectedTerms=("ninety two percent",),
            minimumCitations=1,
            spaceCode="KNOWLEDGE_SPACE",
            latencyBudgetMs=1000,
            costBudget="0.01",
        )
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertEqual(report.run.verdict, "PASS")
        result = report.results[0]
        self.assertGreater(result.metrics["GROUNDEDNESS"], 0.9)
        self.assertEqual(result.metrics["CITATION_COVERAGE"], 1.0)
        self.assertGreater(result.citationCount, 0)

    def testAQuestionWithNoEvidenceIsGradedAsAFailure(self) -> None:
        self.registerCase(
            "UNKNOWN_TOPIC",
            question="what is the corporate travel policy",
            expectedTerms=("travel policy",),
            minimumCitations=1,
            spaceCode="KNOWLEDGE_SPACE",
        )
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        result = next(item for item in report.results if item.caseCode == "UNKNOWN_TOPIC")
        self.assertEqual(result.verdict, "FAIL")

    def testTheAdapterCarriesCitationsAndContextIntoTheObservation(self) -> None:
        self.registerCase(
            "MAINTENANCE",
            question="why was line two halted",
            expectedTerms=("maintenance downtime",),
            minimumCitations=1,
            spaceCode="KNOWLEDGE_SPACE",
        )
        report = self.service.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        result = next(item for item in report.results if item.caseCode == "MAINTENANCE")
        self.assertGreater(result.metrics["GROUNDEDNESS"], 0.5)
        self.assertGreater(result.citationCount, 0)
