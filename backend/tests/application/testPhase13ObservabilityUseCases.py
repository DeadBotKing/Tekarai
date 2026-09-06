"""Phase 13-W application tests — observability over a real SQLite DB.

Covers collection through registered contributors, the degradation path
when one contributor breaks, Prometheus exposition, alert firing with
de-duplication and recovery, acknowledgement, the health report, tenant
isolation, retention, the fail-closed switch, the Phase 13-O audit trail,
and the Phase 13-P ``MONITORING`` job.

The final class wires the **real** Phase 13-U evaluation service and
Phase 13-V feedback service in as contributors, so the §34 metrics come
from the platform's own recorded facts rather than from fixtures.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from django.test import TestCase

from apps.ai.application.services.auditService import AuditApplicationService, AuditSettings
from apps.ai.application.services.evaluationService import (
    EvaluationApplicationService,
    EvaluationSettings,
    RegisterCaseCommand,
    RunSuiteCommand,
)
from apps.ai.application.services.feedbackService import (
    FeedbackApplicationService,
    FeedbackSettings,
    SubmitFeedbackCommand,
)
from apps.ai.application.services.observabilityService import (
    AUDIT_ALERT_ACKNOWLEDGED,
    AUDIT_ALERT_FIRED,
    AUDIT_ALERT_RESOLVED,
    EvaluationMetricsContributor,
    FeedbackMetricsContributor,
    MetricsCollectionJobHandler,
    ObservabilityApplicationService,
    ObservabilitySettings,
    QueueMetricsContributor,
)
from apps.ai.application.services.queueService import (
    QueueApplicationService,
    QueueSettings,
    SubmitJobCommand,
)
from apps.ai.domain.exceptions import (
    AIAlertNotFound,
    AIConfigurationError,
    AIMetricInvalid,
    AIObservabilityWindowInvalid,
)
from apps.ai.domain.services.evaluationEngine import CaseObservation
from apps.ai.domain.services.observabilityEngine import MetricWindow
from apps.ai.domain.valueObjects.observabilityTypes import AlertRule, MetricSample
from apps.ai.infrastructure.models import AIAlertEventModel, AIMetricSnapshotModel
from apps.ai.infrastructure.repositories.auditRepositories import (
    DjangoAuditRecordStore,
    DjangoGovernancePolicyStore,
    DjangoRetentionPurger,
)
from apps.ai.infrastructure.repositories.evaluationRepositories import (
    DjangoEvaluationCaseStore,
    DjangoEvaluationRunStore,
)
from apps.ai.infrastructure.repositories.feedbackRepositories import DjangoFeedbackStore
from apps.ai.infrastructure.repositories.observabilityRepositories import (
    DjangoAlertEventStore,
    DjangoMetricSnapshotStore,
)
from apps.ai.infrastructure.repositories.queueRepositories import DjangoJobStore

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class StaticContributor:
    """Contributor double that reports a fixed sample set."""

    def __init__(
        self, label: str, values: dict[str, float], *, latencies: tuple[float, ...] = ()
    ) -> None:
        self.label = label
        self.values = values
        self.latencies = latencies
        self.calls = 0

    def name(self) -> str:
        return self.label

    def collect(self, tenantId: Any, window: Any) -> tuple[MetricSample, ...]:
        self.calls += 1
        return tuple(
            MetricSample(name=name, value=value, at=getattr(window, "end", None))
            for name, value in self.values.items()
        )


class BrokenContributor:
    def name(self) -> str:
        return "BROKEN"

    def collect(self, tenantId: Any, window: Any) -> tuple[MetricSample, ...]:
        raise RuntimeError("source exploded")


class ObservabilityTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.clock = CLOCK
        self.snapshotStore = DjangoMetricSnapshotStore()
        self.alertStore = DjangoAlertEventStore()
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=AuditSettings(enabled=True, retentionDays=365),
            now=lambda: CLOCK,
        )
        self.service = self.buildService()

    def buildService(self, **overrides: Any) -> ObservabilityApplicationService:
        settings = ObservabilitySettings(
            enabled=overrides.pop("enabled", True),
            collectionWindowMinutes=overrides.pop("collectionWindowMinutes", 60),
            maxWindowHours=overrides.pop("maxWindowHours", 24),
            alertingEnabled=overrides.pop("alertingEnabled", True),
            errorRatioThreshold=overrides.pop("errorRatioThreshold", 0.1),
            latencyP95ThresholdMs=overrides.pop("latencyP95ThresholdMs", 15_000),
            queueDepthThreshold=overrides.pop("queueDepthThreshold", 100),
            feedbackScoreThreshold=overrides.pop("feedbackScoreThreshold", 0.5),
            evaluationScoreThreshold=overrides.pop("evaluationScoreThreshold", 0.6),
            snapshotRetentionDays=overrides.pop("snapshotRetentionDays", 90),
            alertRetentionDays=overrides.pop("alertRetentionDays", 365),
        )
        return ObservabilityApplicationService(
            self.snapshotStore,
            self.alertStore,
            contributors=overrides.pop("contributors", ()),
            settings=settings,
            auditLogger=overrides.pop("auditLogger", self.audit),
            now=lambda: self.clock,
        )

    def window(self, minutes: int = 60) -> MetricWindow:
        return MetricWindow(start=self.clock - timedelta(minutes=minutes), end=self.clock)

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class CollectionTests(ObservabilityTestCase):
    def testContributorsAreMergedIntoOneSnapshot(self) -> None:
        self.service.registerContributor(
            StaticContributor("USAGE", {"aiRequestsTotal": 20, "aiRequestsFailed": 1})
        )
        self.service.registerContributor(StaticContributor("QUEUE", {"aiQueueDepth": 3}))
        result = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(result.snapshot.valueFor("aiRequestsTotal"), 20.0)
        self.assertEqual(result.snapshot.valueFor("aiQueueDepth"), 3.0)
        self.assertEqual(result.snapshot.valueFor("aiErrorRatio"), 0.05)
        self.assertEqual(AIMetricSnapshotModel.objects.count(), 1)
        self.assertFalse(result.isDegraded)

    def testLatencyPercentilesComeFromRawSamples(self) -> None:
        self.service.registerContributor(
            StaticContributor("USAGE", {"aiRequestsTotal": 3}, latencies=(100.0, 200.0, 5000.0))
        )
        result = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(result.snapshot.valueFor("aiLatencyP95"), 5000.0)
        self.assertGreater(result.snapshot.valueFor("aiLatencyAverage"), 0)

    def testABrokenContributorDegradesTheWindowInsteadOfLosingIt(self) -> None:
        self.service.registerContributor(StaticContributor("USAGE", {"aiRequestsTotal": 5}))
        self.service.registerContributor(BrokenContributor())
        result = self.service.collect(self.tenantId, window=self.window())
        self.assertTrue(result.isDegraded)
        self.assertEqual(result.failedSources[0][0], "BROKEN")
        self.assertEqual(result.snapshot.valueFor("aiRequestsTotal"), 5.0)
        self.assertEqual(result.snapshot.metadata["failedSources"], ["BROKEN"])

    def testTwoContributorsPublishingTheSameSeriesIsAWiringBug(self) -> None:
        self.service.registerContributor(StaticContributor("A", {"aiRequestsTotal": 1}))
        self.service.registerContributor(StaticContributor("B", {"aiRequestsTotal": 2}))
        with self.assertRaises(AIMetricInvalid):
            self.service.collect(self.tenantId, window=self.window())

    def testTheDefaultWindowFollowsConfiguration(self) -> None:
        service = self.buildService(collectionWindowMinutes=15)
        produced = service.defaultWindow(now=CLOCK)
        self.assertEqual(produced.durationSeconds, 900.0)

    def testAnAbsurdlyWideWindowIsRefused(self) -> None:
        service = self.buildService(maxWindowHours=1)
        with self.assertRaises(AIObservabilityWindowInvalid):
            service.collect(self.tenantId, window=self.window(minutes=180))

    def testAForeignContributorIsRefusedAtRegistration(self) -> None:
        with self.assertRaises(AIMetricInvalid):
            self.service.registerContributor(object())  # type: ignore[arg-type]

    def testCollectingWithNoContributorsStillProducesASnapshot(self) -> None:
        result = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(result.snapshot.sampleCount, 1)
        self.assertEqual(result.snapshot.valueFor("aiErrorRatio"), 0.0)

    def testDisabledPlatformRefusesEverything(self) -> None:
        disabled = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            disabled.collect(self.tenantId)
        with self.assertRaises(AIConfigurationError):
            disabled.exportPrometheus(self.tenantId)


class ExpositionTests(ObservabilityTestCase):
    def testTheLatestSnapshotIsExposed(self) -> None:
        self.service.registerContributor(
            StaticContributor("USAGE", {"aiRequestsTotal": 7, "aiCostTotal": 1.25})
        )
        self.service.collect(self.tenantId, window=self.window())
        text = self.service.exportPrometheus(self.tenantId)
        self.assertIn("# TYPE aiRequestsTotal counter", text)
        self.assertIn("aiRequestsTotal 7.0", text)
        self.assertIn("aiCostTotal 1.25", text)

    def testExplicitSamplesBypassTheStore(self) -> None:
        text = self.service.exportPrometheus(
            self.tenantId, samples=[MetricSample(name="aiQueueDepth", value=9)]
        )
        self.assertIn("aiQueueDepth 9.0", text)

    def testATenantWithoutDataExposesNothing(self) -> None:
        self.assertEqual(self.service.exportPrometheus(self.otherTenantId), "")


class AlertingTests(ObservabilityTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.usage = StaticContributor("USAGE", {"aiRequestsTotal": 100, "aiRequestsFailed": 40})
        self.service.registerContributor(self.usage)

    def testABreachFiresOneAlertAndAuditsIt(self) -> None:
        result = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(len(result.openedAlerts), 1)
        alert = result.openedAlerts[0]
        self.assertEqual(alert.ruleCode, "AI_ERROR_RATIO_HIGH")
        self.assertEqual(alert.severity, "CRITICAL")
        self.assertEqual(AIAlertEventModel.objects.count(), 1)
        self.assertIn(AUDIT_ALERT_FIRED, self.auditActions())

    def testASustainedBreachDoesNotSpamAlerts(self) -> None:
        self.service.collect(self.tenantId, window=self.window())
        self.clock = CLOCK + timedelta(minutes=5)
        second = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(second.openedAlerts, ())
        self.assertEqual(AIAlertEventModel.objects.count(), 1)

    def testRecoveryResolvesTheAlert(self) -> None:
        self.service.collect(self.tenantId, window=self.window())
        self.usage.values = {"aiRequestsTotal": 100, "aiRequestsFailed": 0}
        self.clock = CLOCK + timedelta(minutes=10)
        recovered = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(len(recovered.resolvedAlerts), 1)
        self.assertIn(AUDIT_ALERT_RESOLVED, self.auditActions())
        self.assertEqual(
            self.service.listAlerts(self.tenantId, states=("RESOLVED",))[0].state, "RESOLVED"
        )

    def testANewBreachAfterRecoveryOpensASecondAlert(self) -> None:
        self.service.collect(self.tenantId, window=self.window())
        self.usage.values = {"aiRequestsTotal": 100, "aiRequestsFailed": 0}
        self.clock = CLOCK + timedelta(minutes=10)
        self.service.collect(self.tenantId, window=self.window())
        self.usage.values = {"aiRequestsTotal": 100, "aiRequestsFailed": 50}
        self.clock = CLOCK + timedelta(minutes=20)
        third = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(len(third.openedAlerts), 1)
        self.assertEqual(AIAlertEventModel.objects.count(), 2)

    def testAlertingCanBeDisabled(self) -> None:
        service = self.buildService(alertingEnabled=False, contributors=[self.usage])
        result = service.collect(self.tenantId, window=self.window())
        self.assertIsNone(result.evaluation)
        self.assertEqual(AIAlertEventModel.objects.count(), 0)

    def testThresholdsComeFromConfiguration(self) -> None:
        service = self.buildService(errorRatioThreshold=0.9, contributors=[self.usage])
        result = service.collect(self.tenantId, window=self.window())
        self.assertEqual(result.openedAlerts, ())

    def testAlertsCanBeAcknowledged(self) -> None:
        alert = self.service.collect(self.tenantId, window=self.window()).openedAlerts[0]
        actor = uuid.uuid4()
        acknowledged = self.service.acknowledgeAlert(self.tenantId, alert.id, actorId=actor)
        self.assertEqual(acknowledged.state, "ACKNOWLEDGED")
        self.assertEqual(acknowledged.acknowledgedBy, actor)
        self.assertIn(AUDIT_ALERT_ACKNOWLEDGED, self.auditActions())

    def testAnAcknowledgedAlertStillResolvesOnRecovery(self) -> None:
        alert = self.service.collect(self.tenantId, window=self.window()).openedAlerts[0]
        self.service.acknowledgeAlert(self.tenantId, alert.id)
        self.usage.values = {"aiRequestsTotal": 100, "aiRequestsFailed": 0}
        self.clock = CLOCK + timedelta(minutes=10)
        recovered = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(len(recovered.resolvedAlerts), 1)

    def testAlertsAreListedAndFiltered(self) -> None:
        self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(len(self.service.listAlerts(self.tenantId)), 1)
        self.assertEqual(len(self.service.listAlerts(self.tenantId, severities=("CRITICAL",))), 1)
        self.assertEqual(
            len(self.service.listAlerts(self.tenantId, ruleCode="AI_QUEUE_BACKLOG")), 0
        )

    def testUnknownAlertIsNotFound(self) -> None:
        with self.assertRaises(AIAlertNotFound):
            self.service.describeAlert(self.tenantId, uuid.uuid4())
        with self.assertRaises(AIAlertNotFound):
            self.service.acknowledgeAlert(self.tenantId, uuid.uuid4())

    def testCustomRulesCanBeEvaluatedDirectly(self) -> None:
        evaluation = self.service.evaluateAlerts(
            self.tenantId,
            [MetricSample(name="aiTokensTotal", value=1_000_000)],
            rules=[
                AlertRule(
                    code="TOKEN_BURN",
                    metric="aiTokensTotal",
                    comparison="ABOVE",
                    threshold=500_000,
                    severity="WARNING",
                )
            ],
        )
        self.assertEqual(len(evaluation.opened), 1)
        self.assertEqual(evaluation.opened[0].ruleCode, "TOKEN_BURN")


class HealthTests(ObservabilityTestCase):
    def testHealthReflectsTheLatestSnapshot(self) -> None:
        self.service.registerContributor(
            StaticContributor(
                "ALL",
                {
                    "aiRequestsTotal": 100,
                    "aiRequestsFailed": 0,
                    "aiQueueDepth": 1,
                    "aiRetrievalDenied": 0,
                    "aiEvaluationScore": 0.95,
                    "aiFeedbackScore": 0.9,
                },
            )
        )
        self.service.collect(self.tenantId, window=self.window())
        report = self.service.healthReport(self.tenantId)
        self.assertEqual(report.status, "HEALTHY")
        self.assertEqual(report.activeAlerts, 0)

    def testAFiringCriticalAlertMakesThePlatformUnhealthy(self) -> None:
        self.service.registerContributor(
            StaticContributor("USAGE", {"aiRequestsTotal": 100, "aiRequestsFailed": 40})
        )
        self.service.collect(self.tenantId, window=self.window())
        report = self.service.healthReport(self.tenantId)
        self.assertEqual(report.status, "UNHEALTHY")
        self.assertEqual(report.criticalAlerts, 1)

    def testATenantWithoutDataIsUnknown(self) -> None:
        report = self.service.healthReport(self.otherTenantId)
        self.assertEqual(report.status, "UNKNOWN")


class IsolationAndRetentionTests(ObservabilityTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.service.registerContributor(
            StaticContributor("USAGE", {"aiRequestsTotal": 100, "aiRequestsFailed": 40})
        )
        self.service.collect(self.tenantId, window=self.window())

    def testSnapshotsAndAlertsAreTenantScoped(self) -> None:
        self.assertIsNone(self.service.latestSnapshot(self.otherTenantId))
        self.assertEqual(self.service.listAlerts(self.otherTenantId), ())
        self.assertEqual(self.service.exportPrometheus(self.otherTenantId), "")

    def testSnapshotsAreListedNewestFirst(self) -> None:
        self.clock = CLOCK + timedelta(hours=1)
        self.service.collect(self.tenantId, window=self.window())
        snapshots = self.service.listSnapshots(self.tenantId)
        self.assertEqual(len(snapshots), 2)
        self.assertGreater(snapshots[0].windowEnd, snapshots[1].windowEnd)

    def testRetentionRemovesOldSnapshotsAndSettledAlerts(self) -> None:
        future = CLOCK + timedelta(days=500)
        removed = self.service.purgeObservabilityRetention(self.tenantId, now=future)
        self.assertEqual(removed["snapshots"], 1)
        # the alert is still firing, so it is deliberately spared
        self.assertEqual(removed["alerts"], 0)
        self.assertEqual(AIAlertEventModel.objects.count(), 1)

    def testAResolvedAlertIsEventuallyPurged(self) -> None:
        alert = self.service.listAlerts(self.tenantId)[0]
        stored = self.alertStore.getAlert(self.tenantId, alert.alertId)
        assert stored is not None
        stored.resolve(now=CLOCK)
        self.alertStore.updateAlert(stored)
        future = CLOCK + timedelta(days=500)
        removed = self.service.purgeObservabilityRetention(self.tenantId, now=future)
        self.assertEqual(removed["alerts"], 1)

    def testRetentionRejectsAnImpossibleHorizon(self) -> None:
        with self.assertRaises(AIConfigurationError):
            self.service.purgeObservabilityRetention(self.tenantId, snapshotDays=0)

    def testAuditChainStaysVerifiable(self) -> None:
        actions = self.auditActions()
        self.assertIn(AUDIT_ALERT_FIRED, actions)
        self.assertEqual(self.audit.verifyTenantChain(self.tenantId), len(actions))


class MonitoringJobTests(ObservabilityTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.service.registerContributor(
            StaticContributor("USAGE", {"aiRequestsTotal": 10, "aiRequestsFailed": 0})
        )
        self.queue = QueueApplicationService(
            DjangoJobStore(),
            auditService=self.audit,
            queueSettings=QueueSettings(enabled=True, defaultMaxAttempts=2, claimLimit=5),
            workerId="testWorker",
            now=lambda: CLOCK,
        )
        self.queue.registerHandler(MetricsCollectionJobHandler(self.service))

    def testCollectionRunsThroughTheQueue(self) -> None:
        descriptor = self.queue.submitJob(
            SubmitJobCommand(
                tenantId=self.tenantId,
                kind="MONITORING",
                payload={"windowMinutes": 30, "evaluateAlerts": True},
            )
        )
        report = self.queue.runOnce()
        self.assertEqual(report.succeeded, 1)
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "SUCCEEDED")
        self.assertGreater(settled.resultSummary["metrics"], 0)
        self.assertEqual(settled.resultSummary["opened"], 0)
        self.assertEqual(AIMetricSnapshotModel.objects.count(), 1)

    def testAnInvalidWindowFailsTheJobNotTheWorker(self) -> None:
        descriptor = self.queue.submitJob(
            SubmitJobCommand(
                tenantId=self.tenantId, kind="MONITORING", payload={"windowMinutes": "hour"}
            )
        )
        self.queue.runOnce()
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.errorCode, "AI_OBSERVABILITY_WINDOW_INVALID")

    def testHandlerAdvertisesItsKind(self) -> None:
        self.assertEqual(MetricsCollectionJobHandler(self.service).kind(), "MONITORING")


class RealContributorTests(ObservabilityTestCase):
    """The §34 metrics coming from the platform's own recorded facts."""

    def setUp(self) -> None:
        super().setUp()
        self.evaluation = EvaluationApplicationService(
            DjangoEvaluationCaseStore(),
            DjangoEvaluationRunStore(),
            producer=self,
            settings=EvaluationSettings(minimumOverallScore=0.5, maximumWarnRatio=1.0),
            now=lambda: CLOCK,
        )
        self.feedback = FeedbackApplicationService(
            DjangoFeedbackStore(),
            settings=FeedbackSettings(promotionThreshold=1),
            now=lambda: CLOCK,
        )
        self.queueService = QueueApplicationService(
            DjangoJobStore(),
            queueSettings=QueueSettings(enabled=True, claimLimit=5),
            workerId="metricsWorker",
            now=lambda: CLOCK,
        )
        self.service = self.buildService(
            contributors=[
                QueueMetricsContributor(self.queueService),
                EvaluationMetricsContributor(self.evaluation),
                FeedbackMetricsContributor(self.feedback),
            ]
        )

    # doubles as the evaluation AnswerProducer
    def produce(self, tenantId: Any, case: Any) -> CaseObservation:
        return CaseObservation(
            answer="Production output reached ninety two percent.",
            contextText="Production output reached ninety two percent of the plan.",
            citationCount=1,
            latencyMs=30,
        )

    def testQueueDepthComesFromTheRealQueue(self) -> None:
        for index in range(3):
            self.queueService.submitJob(
                SubmitJobCommand(tenantId=self.tenantId, kind="GENERIC", payload={"index": index})
            )
        result = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(result.snapshot.valueFor("aiQueueDepth"), 3.0)
        self.assertEqual(result.snapshot.valueFor("aiJobsFailed"), 0.0)

    def testEvaluationScoreComesFromTheRealRun(self) -> None:
        self.evaluation.registerCase(
            self.tenantId,
            RegisterCaseCommand(
                suiteCode="RAG_GOLDEN",
                caseCode="OUTPUT",
                question="what was the production output",
                expectedTerms=("ninety two percent",),
            ),
        )
        self.evaluation.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        result = self.service.collect(self.tenantId, window=self.window())
        self.assertGreater(result.snapshot.valueFor("aiEvaluationScore"), 0.5)
        self.assertEqual(result.snapshot.valueFor("aiEvaluationFailures"), 0.0)

    def testFeedbackScoreComesFromRealSignals(self) -> None:
        for rating in (5, 4):
            self.feedback.submitFeedback(
                self.tenantId,
                SubmitFeedbackCommand(
                    requestId=uuid.uuid4(),
                    responseId=uuid.uuid4(),
                    userId=uuid.uuid4(),
                    kind="RATING",
                    rating=rating,
                ),
            )
        # Windows are half-open, so collection runs after the events it
        # measures — exactly as a scheduled sweep would.
        self.clock = CLOCK + timedelta(minutes=1)
        result = self.service.collect(self.tenantId, window=self.window(minutes=120))
        self.assertGreater(result.snapshot.valueFor("aiFeedbackScore"), 0.5)

    def testAFailingSuiteMakesThePlatformUnhealthy(self) -> None:
        self.evaluation.registerCase(
            self.tenantId,
            RegisterCaseCommand(
                suiteCode="RAG_GOLDEN",
                caseCode="IMPOSSIBLE",
                question="what is the corporate travel policy",
                expectedTerms=("travel policy",),
            ),
        )
        self.evaluation.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        result = self.service.collect(self.tenantId, window=self.window())
        self.assertEqual(result.snapshot.valueFor("aiEvaluationFailures"), 1.0)
        report = self.service.healthReport(self.tenantId)
        self.assertEqual(report.status, "UNHEALTHY")
        evaluation = report.componentFor("EVALUATION")
        assert evaluation is not None
        self.assertIn("failing", evaluation.reason)

    def testTheRealEvaluationScoreDrivesTheAlertRule(self) -> None:
        # The same run, graded against a stricter alert threshold: the alert
        # fires on the platform's real score, not on a fixture.
        service = self.buildService(
            evaluationScoreThreshold=0.9,
            contributors=[EvaluationMetricsContributor(self.evaluation)],
        )
        self.evaluation.registerCase(
            self.tenantId,
            RegisterCaseCommand(
                suiteCode="RAG_GOLDEN",
                caseCode="IMPOSSIBLE",
                question="what is the corporate travel policy",
                expectedTerms=("travel policy",),
            ),
        )
        run = self.evaluation.runSuite(self.tenantId, RunSuiteCommand(suiteCode="RAG_GOLDEN"))
        self.assertLess(run.summary.overallScore, 0.9)
        result = service.collect(self.tenantId, window=self.window())
        codes = {alert.ruleCode for alert in result.openedAlerts}
        self.assertIn("AI_EVALUATION_LOW", codes)

    def testTheWholeExpositionIsRenderedFromRealFacts(self) -> None:
        self.queueService.submitJob(
            SubmitJobCommand(tenantId=self.tenantId, kind="GENERIC", payload={})
        )
        self.service.collect(self.tenantId, window=self.window())
        text = self.service.exportPrometheus(self.tenantId)
        self.assertIn("aiQueueDepth 1.0", text)
        self.assertIn("# TYPE aiQueueDepth gauge", text)
