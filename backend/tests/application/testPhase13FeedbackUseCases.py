"""Phase 13-V application tests — feedback over a real SQLite database.

Covers idempotent submission and revision, the triage lifecycle, the
promotion policy, per-target aggregation, the satisfaction trend, the
backlog view, retention, tenant isolation, the fail-closed switch, the
Phase 13-O audit trail, and the Phase 13-P ``FEEDBACK`` sweep job.

The final class closes the loop the whole phase has been building toward:
a human complaint becomes a **real Phase 13-U golden case**, and the very
next evaluation run grades the platform against it.
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
    RunSuiteCommand,
)
from apps.ai.application.services.feedbackService import (
    AUDIT_FEEDBACK_PROMOTED,
    AUDIT_FEEDBACK_RECEIVED,
    AUDIT_FEEDBACK_TRIAGED,
    FeedbackApplicationService,
    FeedbackPromotionJobHandler,
    FeedbackSettings,
    SubmitFeedbackCommand,
)
from apps.ai.application.services.queueService import (
    QueueApplicationService,
    QueueSettings,
    SubmitJobCommand,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIFeedbackInvalid,
    AIFeedbackNotFound,
    AIFeedbackNotPromotable,
)
from apps.ai.domain.services.evaluationEngine import CaseObservation
from apps.ai.infrastructure.models import AIFeedbackEntryModel
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
from apps.ai.infrastructure.repositories.queueRepositories import DjangoJobStore
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)


class RecordingPublisher:
    """Golden-case publisher double that records what V would register."""

    def __init__(self) -> None:
        self.commands: list[Any] = []

    def registerCase(self, tenantId: Any, command: Any) -> Any:
        self.commands.append(command)
        return command


class FeedbackTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.userId = uuid.uuid4()
        self.otherUserId = uuid.uuid4()
        self.clock = CLOCK
        self.store = DjangoFeedbackStore()
        self.publisher = RecordingPublisher()
        self.audit = AuditApplicationService(
            DjangoAuditRecordStore(),
            DjangoGovernancePolicyStore(),
            DjangoRetentionPurger(),
            auditSettings=AuditSettings(enabled=True, retentionDays=365),
            now=lambda: CLOCK,
        )
        self.service = self.buildService()

    def buildService(self, **overrides: Any) -> FeedbackApplicationService:
        settings = FeedbackSettings(
            enabled=overrides.pop("enabled", True),
            promotionThreshold=overrides.pop("promotionThreshold", 1),
            requireCorrection=overrides.pop("requireCorrection", True),
            requireReason=overrides.pop("requireReason", True),
            negativeRatingCeiling=overrides.pop("negativeRatingCeiling", 2),
            minimumSatisfaction=overrides.pop("minimumSatisfaction", 0.6),
            trendTolerance=overrides.pop("trendTolerance", 0.05),
            trendWindowDays=overrides.pop("trendWindowDays", 7),
            goldenSuiteCode=overrides.pop("goldenSuiteCode", "FEEDBACK_GOLDEN"),
            retentionDays=overrides.pop("retentionDays", 730),
        )
        return FeedbackApplicationService(
            self.store,
            casePublisher=overrides.pop("casePublisher", self.publisher),
            settings=settings,
            auditLogger=overrides.pop("auditLogger", self.audit),
            now=lambda: self.clock,
        )

    def submit(self, **overrides: Any) -> Any:
        params: dict[str, Any] = {
            "requestId": uuid.uuid4(),
            "responseId": uuid.uuid4(),
            "userId": self.userId,
            "kind": "RATING",
            "rating": 2,
            "reason": "UNGROUNDED",
            "correction": "Line one reached ninety two percent.",
            "question": "what was the production output",
            "modelCode": "GPT_TEST",
            "promptVersion": "3",
        }
        params.update(overrides)
        return self.service.submitFeedback(self.tenantId, SubmitFeedbackCommand(**params))

    def auditActions(self) -> list[str]:
        return [entry.action for entry in self.audit.listAuditEntries(self.tenantId)]


class SubmissionTests(FeedbackTestCase):
    def testFirstSignalIsStored(self) -> None:
        result = self.submit()
        self.assertTrue(result.created)
        self.assertEqual(result.feedback.sentiment, "NEGATIVE")
        self.assertEqual(result.feedback.status, "NEW")
        self.assertEqual(result.feedback.targetKey, "GPT_TEST@3")
        self.assertEqual(result.feedback.suggestedMetric, "GROUNDEDNESS")
        self.assertEqual(AIFeedbackEntryModel.objects.count(), 1)
        self.assertIn(AUDIT_FEEDBACK_RECEIVED, self.auditActions())

    def testTheSameSignalTwiceDoesNotStuffTheBallotBox(self) -> None:
        first = self.submit(requestId=uuid.UUID(int=1), responseId=uuid.UUID(int=2))
        second = self.submit(requestId=uuid.UUID(int=1), responseId=uuid.UUID(int=2))
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertTrue(second.isDuplicate)
        self.assertEqual(AIFeedbackEntryModel.objects.count(), 1)

    def testAChangeOfMindRevisesTheSameSlot(self) -> None:
        request, response = uuid.UUID(int=3), uuid.UUID(int=4)
        self.submit(requestId=request, responseId=response, rating=1)
        revised = self.submit(
            requestId=request, responseId=response, rating=5, reason="", correction=""
        )
        self.assertTrue(revised.revised)
        self.assertEqual(revised.feedback.rating, 5)
        self.assertEqual(revised.feedback.sentiment, "POSITIVE")
        self.assertEqual(AIFeedbackEntryModel.objects.count(), 1)

    def testTwoUsersLeaveTwoSignals(self) -> None:
        request, response = uuid.UUID(int=5), uuid.UUID(int=6)
        self.submit(requestId=request, responseId=response)
        self.submit(requestId=request, responseId=response, userId=self.otherUserId)
        self.assertEqual(AIFeedbackEntryModel.objects.count(), 2)

    def testDifferentKindsCoexistForOneUser(self) -> None:
        request, response = uuid.UUID(int=7), uuid.UUID(int=8)
        self.submit(requestId=request, responseId=response, kind="RATING")
        self.submit(
            requestId=request,
            responseId=response,
            kind="FLAG",
            rating=None,
            reason="UNSAFE",
            correction="",
        )
        self.assertEqual(AIFeedbackEntryModel.objects.count(), 2)

    def testThumbsAndCommentsAreAcceptedWithoutARating(self) -> None:
        thumbs = self.submit(
            kind="THUMBS", rating=None, sentiment="POSITIVE", reason="", correction=""
        )
        self.assertEqual(thumbs.feedback.sentiment, "POSITIVE")
        comment = self.submit(
            kind="COMMENT", rating=None, reason="", correction="", comment="Nice format."
        )
        self.assertEqual(comment.feedback.sentiment, "NEUTRAL")

    def testInvalidSubmissionsAreRejected(self) -> None:
        with self.assertRaises(AIFeedbackInvalid):
            self.service.submitFeedback(self.tenantId, "feedback")  # type: ignore[arg-type]
        with self.assertRaises(ValidationFailedError):
            self.submit(rating=9)
        with self.assertRaises(ValidationFailedError):
            self.submit(kind="RATING", rating=None)

    def testDisabledPlatformRefusesEverything(self) -> None:
        disabled = self.buildService(enabled=False)
        with self.assertRaises(AIConfigurationError):
            disabled.submitFeedback(
                self.tenantId, SubmitFeedbackCommand(requestId=uuid.uuid4(), rating=3)
            )
        with self.assertRaises(AIConfigurationError):
            disabled.listFeedback(self.tenantId)


class TriageTests(FeedbackTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.entry = self.submit().feedback

    def testAcceptingMovesTheSignalForward(self) -> None:
        accepted = self.service.acceptFeedback(
            self.tenantId, self.entry.feedbackId, reviewerId=self.otherUserId
        )
        self.assertEqual(accepted.status, "ACCEPTED")
        self.assertIn(AUDIT_FEEDBACK_TRIAGED, self.auditActions())

    def testRejectingRecordsTheReason(self) -> None:
        rejected = self.service.rejectFeedback(
            self.tenantId, self.entry.feedbackId, "Duplicate report."
        )
        self.assertEqual(rejected.status, "REJECTED")
        self.assertEqual(rejected.rejectionReason, "Duplicate report.")

    def testRejectingWithoutAReasonIsRefused(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.service.rejectFeedback(self.tenantId, self.entry.feedbackId, "  ")

    def testATerminalSignalCannotBeTriagedAgain(self) -> None:
        self.service.rejectFeedback(self.tenantId, self.entry.feedbackId, "no")
        with self.assertRaises(ValidationFailedError):
            self.service.acceptFeedback(self.tenantId, self.entry.feedbackId)

    def testRevisingATerminalSignalIsIgnoredNotApplied(self) -> None:
        self.service.rejectFeedback(self.tenantId, self.entry.feedbackId, "no")
        again = self.service.submitFeedback(
            self.tenantId,
            SubmitFeedbackCommand(
                requestId=self.entry.requestId,
                responseId=self.entry.responseId,
                userId=self.userId,
                kind="RATING",
                rating=5,
            ),
        )
        self.assertTrue(again.isDuplicate)
        self.assertEqual(
            self.service.describeFeedback(self.tenantId, self.entry.feedbackId).rating, 2
        )

    def testUnknownSignalIsNotFound(self) -> None:
        with self.assertRaises(AIFeedbackNotFound):
            self.service.describeFeedback(self.tenantId, uuid.uuid4())
        with self.assertRaises(AIFeedbackNotFound):
            self.service.acceptFeedback(self.tenantId, uuid.uuid4())

    def testBacklogCountsEveryState(self) -> None:
        self.submit(requestId=uuid.uuid4(), responseId=uuid.uuid4())
        self.service.acceptFeedback(self.tenantId, self.entry.feedbackId)
        backlog = self.service.triageBacklog(self.tenantId)
        self.assertEqual(backlog.get("ACCEPTED"), 1)
        self.assertEqual(backlog.get("NEW"), 1)


class PromotionTests(FeedbackTestCase):
    def testAnAcceptedComplaintBecomesAGoldenCase(self) -> None:
        entry = self.submit().feedback
        self.service.acceptFeedback(self.tenantId, entry.feedbackId)
        promoted = self.service.promoteFeedback(self.tenantId, entry.feedbackId)
        self.assertEqual(promoted.status, "PROMOTED")
        self.assertTrue(promoted.promotedCaseCode)
        self.assertEqual(len(self.publisher.commands), 1)
        command = self.publisher.commands[0]
        self.assertEqual(command.suiteCode, "FEEDBACK_GOLDEN")
        self.assertEqual(command.question, "what was the production output")
        self.assertEqual(command.metadata["origin"], "FEEDBACK")
        self.assertIn(AUDIT_FEEDBACK_PROMOTED, self.auditActions())

    def testAPositiveSignalIsNotPromotable(self) -> None:
        entry = self.submit(rating=5, reason="", correction="").feedback
        with self.assertRaises(AIFeedbackNotPromotable):
            self.service.promoteFeedback(self.tenantId, entry.feedbackId)

    def testAComplaintWithoutACorrectionIsNotPromotable(self) -> None:
        entry = self.submit(correction="").feedback
        with self.assertRaises(AIFeedbackNotPromotable):
            self.service.promoteFeedback(self.tenantId, entry.feedbackId)

    def testPromotionWithoutAPublisherFailsClosed(self) -> None:
        service = self.buildService(casePublisher=None)
        entry = self.submit().feedback
        with self.assertRaises(AIConfigurationError):
            service.promoteFeedback(self.tenantId, entry.feedbackId)

    def testTheSweepPromotesEveryQualifyingComplaint(self) -> None:
        self.submit(question="what was the production output")
        self.submit(
            requestId=uuid.uuid4(),
            responseId=uuid.uuid4(),
            userId=self.otherUserId,
            question="why was line two halted",
            reason="INCOMPLETE",
            correction="Preventive maintenance downtime.",
        )
        result = self.service.runPromotionSweep(self.tenantId)
        self.assertEqual(result.promotedCount, 2)
        self.assertEqual(len(self.publisher.commands), 2)
        self.assertEqual(len(result.promotedFeedbackIds), 2)
        statuses = {item.status for item in self.service.listFeedback(self.tenantId)}
        self.assertEqual(statuses, {"PROMOTED"})

    def testTheSweepIsIdempotent(self) -> None:
        self.submit()
        first = self.service.runPromotionSweep(self.tenantId)
        second = self.service.runPromotionSweep(self.tenantId)
        self.assertEqual(first.promotedCount, 1)
        self.assertEqual(second.promotedCount, 0)
        self.assertEqual(len(self.publisher.commands), 1)

    def testRepeatedComplaintsCollapseIntoOneCase(self) -> None:
        service = self.buildService(promotionThreshold=2)
        for _ in range(3):
            self.submit(requestId=uuid.uuid4(), responseId=uuid.uuid4(), userId=uuid.uuid4())
        result = service.runPromotionSweep(self.tenantId)
        self.assertEqual(result.promotedCount, 1)
        self.assertEqual(result.plan.drafts[0].occurrences, 3)
        self.assertEqual(len(result.promotedFeedbackIds), 3)

    def testAKnownQuestionIsNotPromotedTwice(self) -> None:
        self.submit()
        plan = self.service.planPromotions(
            self.tenantId, knownQuestions=("What was the production output",)
        )
        self.assertEqual(plan.draftCount, 0)
        self.assertIn("already covers", plan.skipped[0][1])

    def testTheDryRunChangesNothing(self) -> None:
        self.submit()
        self.service.planPromotions(self.tenantId)
        self.assertEqual(self.publisher.commands, [])
        self.assertEqual(self.service.listFeedback(self.tenantId)[0].status, "NEW")


class SummaryAndTrendTests(FeedbackTestCase):
    def submitRating(self, rating: int, **overrides: Any) -> Any:
        params: dict[str, Any] = {
            "requestId": uuid.uuid4(),
            "responseId": uuid.uuid4(),
            "userId": uuid.uuid4(),
            "rating": rating,
            "reason": "" if rating >= 3 else "UNGROUNDED",
            "correction": "" if rating >= 3 else "the right answer",
        }
        params.update(overrides)
        return self.submit(**params)

    def testSummaryReportsSatisfactionAndReasons(self) -> None:
        self.submitRating(5)
        self.submitRating(4)
        self.submitRating(1)
        summary = self.service.summarize(self.tenantId)
        self.assertEqual(summary.total, 3)
        self.assertEqual(summary.negative, 1)
        self.assertGreater(summary.satisfaction, 0.5)
        self.assertEqual(summary.topReasons[0][0], "UNGROUNDED")

    def testSummaryCanBeScopedToOneModel(self) -> None:
        self.submitRating(5, modelCode="MODEL_A")
        self.submitRating(1, modelCode="MODEL_B")
        summary = self.service.summarize(self.tenantId, modelCode="MODEL_B")
        self.assertEqual(summary.total, 1)
        self.assertEqual(summary.negative, 1)

    def testTargetBreakdownSeparatesPromptVersions(self) -> None:
        self.submitRating(5, promptVersion="3")
        self.submitRating(1, promptVersion="4")
        summary = self.service.summarize(self.tenantId)
        self.assertEqual(
            {target.targetKey for target in summary.targets}, {"GPT_TEST@3", "GPT_TEST@4"}
        )

    def testAQualityDropAcrossWindowsIsDetected(self) -> None:
        self.clock = CLOCK - timedelta(days=10)
        self.submitRating(5)
        self.submitRating(5)
        self.clock = CLOCK - timedelta(days=1)
        self.submitRating(1)
        self.submitRating(1)
        self.clock = CLOCK
        trend = self.service.compareWindows(self.tenantId, windowDays=7, now=CLOCK)
        self.assertTrue(trend.regressed)
        self.assertLess(trend.satisfactionDelta, 0)

    def testAStableStreamShowsNoTrend(self) -> None:
        self.clock = CLOCK - timedelta(days=10)
        self.submitRating(4)
        self.clock = CLOCK - timedelta(days=1)
        self.submitRating(4)
        self.clock = CLOCK
        trend = self.service.compareWindows(self.tenantId, windowDays=7, now=CLOCK)
        self.assertFalse(trend.regressed)
        self.assertFalse(trend.improved)

    def testAnImpossibleWindowIsRejected(self) -> None:
        with self.assertRaises(AIFeedbackInvalid):
            self.service.compareWindows(self.tenantId, windowDays=0)

    def testListingFiltersByStatusSentimentAndRequest(self) -> None:
        first = self.submitRating(1).feedback
        self.submitRating(5)
        self.service.acceptFeedback(self.tenantId, first.feedbackId)
        self.assertEqual(len(self.service.listFeedback(self.tenantId, statuses=("ACCEPTED",))), 1)
        self.assertEqual(len(self.service.listFeedback(self.tenantId, sentiments=("POSITIVE",))), 1)
        self.assertEqual(
            len(self.service.listFeedback(self.tenantId, requestId=first.requestId)), 1
        )


class IsolationAndRetentionTests(FeedbackTestCase):
    def testFeedbackNeverCrossesTenantBoundaries(self) -> None:
        entry = self.submit().feedback
        self.assertEqual(self.service.listFeedback(self.otherTenantId), ())
        with self.assertRaises(AIFeedbackNotFound):
            self.service.describeFeedback(self.otherTenantId, entry.feedbackId)
        self.assertTrue(self.service.summarize(self.otherTenantId).isEmpty)

    def testRetentionRemovesSettledSignalsOnly(self) -> None:
        pending = self.submit().feedback
        settled = self.submit(requestId=uuid.uuid4(), responseId=uuid.uuid4()).feedback
        self.service.rejectFeedback(self.tenantId, settled.feedbackId, "no")
        future = CLOCK + timedelta(days=900)
        self.assertEqual(self.service.purgeFeedbackRetention(self.tenantId, now=future), 1)
        self.assertTrue(AIFeedbackEntryModel.objects.filter(id=pending.feedbackId).exists())

    def testRetentionRejectsAnImpossibleHorizon(self) -> None:
        with self.assertRaises(AIConfigurationError):
            self.service.purgeFeedbackRetention(self.tenantId, retentionDays=0)

    def testAuditChainStaysVerifiable(self) -> None:
        entry = self.submit().feedback
        self.service.acceptFeedback(self.tenantId, entry.feedbackId)
        self.service.promoteFeedback(self.tenantId, entry.feedbackId)
        actions = self.auditActions()
        self.assertIn(AUDIT_FEEDBACK_RECEIVED, actions)
        self.assertIn(AUDIT_FEEDBACK_TRIAGED, actions)
        self.assertIn(AUDIT_FEEDBACK_PROMOTED, actions)
        self.assertEqual(self.audit.verifyTenantChain(self.tenantId), len(actions))


class PromotionJobTests(FeedbackTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.queue = QueueApplicationService(
            DjangoJobStore(),
            auditService=self.audit,
            queueSettings=QueueSettings(enabled=True, defaultMaxAttempts=2, claimLimit=5),
            workerId="testWorker",
            now=lambda: CLOCK,
        )
        self.queue.registerHandler(FeedbackPromotionJobHandler(self.service))

    def testTheSweepRunsThroughTheQueue(self) -> None:
        self.submit()
        descriptor = self.queue.submitJob(
            SubmitJobCommand(tenantId=self.tenantId, kind="FEEDBACK", payload={"purge": False})
        )
        report = self.queue.runOnce()
        self.assertEqual(report.succeeded, 1)
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.status, "SUCCEEDED")
        self.assertEqual(settled.resultSummary["promoted"], 1)
        self.assertEqual(len(self.publisher.commands), 1)

    def testInvalidPayloadFailsTheJobNotTheWorker(self) -> None:
        descriptor = self.queue.submitJob(
            SubmitJobCommand(
                tenantId=self.tenantId, kind="FEEDBACK", payload={"knownQuestions": "nope"}
            )
        )
        self.queue.runOnce()
        settled = self.queue.describeJob(self.tenantId, descriptor.jobId)
        self.assertEqual(settled.errorCode, "AI_FEEDBACK_INVALID")

    def testHandlerAdvertisesItsKind(self) -> None:
        self.assertEqual(FeedbackPromotionJobHandler(self.service).kind(), "FEEDBACK")


class ClosingTheLoopTests(FeedbackTestCase):
    """A complaint becomes a real Phase 13-U case that then grades the platform."""

    def setUp(self) -> None:
        super().setUp()
        self.evaluation = EvaluationApplicationService(
            DjangoEvaluationCaseStore(),
            DjangoEvaluationRunStore(),
            producer=self,
            settings=EvaluationSettings(minimumOverallScore=0.5, maximumWarnRatio=1.0),
            auditLogger=self.audit,
            now=lambda: CLOCK,
        )
        self.answers: dict[str, CaseObservation] = {}
        self.service = self.buildService(casePublisher=self.evaluation)

    # doubles as the evaluation AnswerProducer
    def produce(self, tenantId: Any, case: Any) -> CaseObservation:
        return self.answers.get(
            case.caseCode,
            CaseObservation(
                # A good answer restates the topic and carries the fact the
                # human supplied as the correction.
                answer=("Production output on line one reached ninety two percent of the plan."),
                contextText="Line one reached ninety two percent of planned production output.",
                citationCount=1,
                latencyMs=20,
            ),
        )

    def testAComplaintBecomesARealGoldenCase(self) -> None:
        entry = self.submit().feedback
        self.service.acceptFeedback(self.tenantId, entry.feedbackId)
        promoted = self.service.promoteFeedback(self.tenantId, entry.feedbackId)
        cases = self.evaluation.listCases(self.tenantId, "FEEDBACK_GOLDEN")
        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].caseCode, promoted.promotedCaseCode)
        self.assertEqual(cases[0].question, "what was the production output")
        self.assertEqual(cases[0].expectedTerms, ("Line one reached ninety two percent.",))

    def testTheNextEvaluationRunGradesTheFixedBehaviour(self) -> None:
        entry = self.submit().feedback
        self.service.promoteFeedback(self.tenantId, entry.feedbackId)
        report = self.evaluation.runSuite(
            self.tenantId, RunSuiteCommand(suiteCode="FEEDBACK_GOLDEN")
        )
        self.assertEqual(report.run.verdict, "PASS")
        self.assertEqual(report.summary.caseCount, 1)
        self.assertEqual(report.results[0].metrics["COMPLETENESS"], 1.0)

    def testARegressionOnThePromotedCaseIsCaught(self) -> None:
        entry = self.submit().feedback
        promoted = self.service.promoteFeedback(self.tenantId, entry.feedbackId)
        self.answers[promoted.promotedCaseCode] = CaseObservation(
            answer="Output data is unavailable at this time.",
            contextText="Line one reached ninety two percent of planned production output.",
            citationCount=1,
        )
        report = self.evaluation.runSuite(
            self.tenantId, RunSuiteCommand(suiteCode="FEEDBACK_GOLDEN")
        )
        self.assertEqual(report.run.verdict, "FAIL")
        self.assertEqual(report.results[0].metrics["COMPLETENESS"], 0.0)

    def testTheSweepFeedsTheSuiteInOnePass(self) -> None:
        self.submit(question="what was the production output")
        self.submit(
            requestId=uuid.uuid4(),
            responseId=uuid.uuid4(),
            userId=self.otherUserId,
            question="why was line two halted",
            reason="INCOMPLETE",
            correction="Preventive maintenance downtime.",
        )
        result = self.service.runPromotionSweep(self.tenantId)
        self.assertEqual(result.promotedCount, 2)
        report = self.evaluation.runSuite(
            self.tenantId, RunSuiteCommand(suiteCode="FEEDBACK_GOLDEN")
        )
        self.assertEqual(report.summary.caseCount, 2)
