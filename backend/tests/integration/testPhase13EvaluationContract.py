"""Phase 13-U integration tests — the evaluation stores over real SQLite.

Covers the ``aiEvaluationCases``, ``aiEvaluationRuns`` and
``aiEvaluationResults`` persistence contract: case round trips with their
budgets and schemas, the natural-key lookup and its uniqueness, suite
listings, run lifecycle persistence, the "latest completed run" lookup
that powers regression detection, bulk result writes with metric-score
fidelity, the one-result-per-case-per-run guarantee, the cascade from run
to results, and the retention sweep that only removes settled runs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.ai.domain.entities.evaluationRecords import (
    AIEvaluationCase,
    AIEvaluationResult,
    AIEvaluationRun,
)
from apps.ai.domain.exceptions import AIEvaluationInvalid
from apps.ai.domain.valueObjects.evaluationTypes import EvaluationCriteria, MetricScore
from apps.ai.infrastructure.models import (
    AIEvaluationCaseModel,
    AIEvaluationResultModel,
    AIEvaluationRunModel,
)
from apps.ai.infrastructure.repositories.evaluationRepositories import (
    DjangoEvaluationCaseStore,
    DjangoEvaluationRunStore,
    caseToEntity,
    resultToEntity,
    runToEntity,
)

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
CRITERIA = EvaluationCriteria.platformDefault()


class DjangoEvaluationCaseStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = DjangoEvaluationCaseStore()

    def case(self, caseCode: str = "PRODUCTION_OUTPUT", **overrides: object) -> AIEvaluationCase:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "suiteCode": overrides.pop("suiteCode", "RAG_GOLDEN"),
            "caseCode": caseCode,
            "question": "what was the production output",
            "expectedTerms": ("ninety two percent",),
            "forbiddenTerms": ("password",),
            "expectedSchema": {"type": "object", "required": ["value"]},
            "minimumCitations": 2,
            "latencyBudgetMs": 1500,
            "costBudget": "0.05",
            "spaceCode": "KNOWLEDGE_SPACE",
            "createdAt": CLOCK,
            "updatedAt": CLOCK,
        }
        params.update(overrides)
        return AIEvaluationCase(**params)

    def testRoundTripPreservesBudgetsAndSchema(self) -> None:
        stored = self.store.saveCase(self.case())
        loaded = self.store.getCase(self.tenantId, stored.id)
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.qualifiedCode, "RAG_GOLDEN:PRODUCTION_OUTPUT")
        self.assertEqual(loaded.expectedTerms, ("ninety two percent",))
        self.assertEqual(loaded.forbiddenTerms, ("password",))
        self.assertEqual(loaded.expectedSchema["required"], ["value"])
        self.assertEqual(loaded.minimumCitations, 2)
        self.assertEqual(loaded.latencyBudgetMs, 1500)
        self.assertEqual(Decimal(loaded.costBudget), Decimal("0.05"))
        self.assertTrue(loaded.expectsStructuredOutput)

    def testFindByNaturalKeyIsNormalizedAndTenantScoped(self) -> None:
        self.store.saveCase(self.case())
        self.assertIsNotNone(self.store.findCase(self.tenantId, "rag_golden", "production_output"))
        self.assertIsNone(
            self.store.findCase(self.otherTenantId, "RAG_GOLDEN", "PRODUCTION_OUTPUT")
        )
        self.assertIsNone(self.store.findCase(self.tenantId, "RAG_GOLDEN", "MISSING"))

    def testOneCasePerSuiteCodeIsEnforcedByTheDatabase(self) -> None:
        self.store.saveCase(self.case())
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveCase(self.case())

    def testTheSameCaseCodeMayExistInTwoSuites(self) -> None:
        self.store.saveCase(self.case())
        self.store.saveCase(self.case(suiteCode="SAFETY_GOLDEN"))
        self.assertEqual(AIEvaluationCaseModel.objects.count(), 2)

    def testUpdatePersistsEveryEditableField(self) -> None:
        stored = self.store.saveCase(self.case())
        stored.question = "updated question"
        stored.minimumCitations = 5
        stored.deactivate(now=CLOCK)
        updated = self.store.updateCase(stored)
        self.assertEqual(updated.question, "updated question")
        self.assertEqual(updated.minimumCitations, 5)
        self.assertFalse(updated.isActive)

    def testUpdatingAnUnknownRowIsRefused(self) -> None:
        with self.assertRaises(AIEvaluationInvalid):
            self.store.updateCase(self.case("GHOST"))

    def testListingFiltersBySuiteAndActivity(self) -> None:
        self.store.saveCase(self.case("A"))
        self.store.saveCase(self.case("B", isActive=False))
        self.store.saveCase(self.case("C", suiteCode="SAFETY_GOLDEN"))
        self.assertEqual(len(self.store.listCases(self.tenantId)), 2)
        self.assertEqual(len(self.store.listCases(self.tenantId, activeOnly=False)), 3)
        self.assertEqual(len(self.store.listCases(self.tenantId, "SAFETY_GOLDEN")), 1)

    def testSuiteListingIsDistinctAndSorted(self) -> None:
        self.store.saveCase(self.case("A", suiteCode="ZULU_SUITE"))
        self.store.saveCase(self.case("B", suiteCode="ALPHA_SUITE"))
        self.store.saveCase(self.case("C", suiteCode="ALPHA_SUITE"))
        self.assertEqual(self.store.listSuites(self.tenantId), ("ALPHA_SUITE", "ZULU_SUITE"))

    def testDeleteIsTenantScoped(self) -> None:
        stored = self.store.saveCase(self.case())
        self.assertEqual(self.store.deleteCase(self.otherTenantId, stored.id), 0)
        self.assertEqual(self.store.deleteCase(self.tenantId, stored.id), 1)

    def testMapperProducesAValidatedEntity(self) -> None:
        self.store.saveCase(self.case())
        row = AIEvaluationCaseModel.objects.get(tenantId=self.tenantId)
        entity = caseToEntity(row)
        self.assertIsInstance(entity, AIEvaluationCase)
        self.assertEqual(entity.suiteCode, "RAG_GOLDEN")


class DjangoEvaluationRunStoreTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.store = DjangoEvaluationRunStore()

    def makeRun(self, **overrides: object) -> AIEvaluationRun:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "suiteCode": overrides.pop("suiteCode", "RAG_GOLDEN"),
            "criteriaSignature": CRITERIA.signature(),
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIEvaluationRun(**params)

    def result(
        self, runId: uuid.UUID, caseCode: str = "PRODUCTION_OUTPUT", **overrides: object
    ) -> AIEvaluationResult:
        params: dict = {
            "tenantId": overrides.pop("tenantId", self.tenantId),
            "runId": runId,
            "caseCode": caseCode,
            "verdict": "PASS",
            "score": 0.91,
            "scores": (
                MetricScore.evaluate("GROUNDEDNESS", 0.95, CRITERIA, detail="ok"),
                MetricScore.evaluate("RELEVANCE", 0.8, CRITERIA),
            ),
            "latencyMs": 120,
            "totalTokens": 44,
            "cost": "0.0012",
            "citationCount": 2,
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIEvaluationResult(**params)

    def testRunRoundTripPreservesTheCriteriaSignature(self) -> None:
        stored = self.store.saveRun(self.makeRun())
        loaded = self.store.getRun(self.tenantId, stored.id)
        assert loaded is not None
        self.assertEqual(loaded.criteriaSignature, CRITERIA.signature())
        self.assertEqual(loaded.status, "PENDING")
        self.assertEqual(loaded.suiteCode, "RAG_GOLDEN")

    def testRunUpdatePersistsTheSettledState(self) -> None:
        stored = self.store.saveRun(self.makeRun())
        stored.transitionTo("RUNNING", now=CLOCK)
        stored.complete(
            verdict="WARN",
            overallScore=0.82,
            passedCount=1,
            warnedCount=1,
            failedCount=0,
            now=CLOCK,
        )
        updated = self.store.updateRun(stored)
        self.assertEqual(updated.status, "COMPLETED")
        self.assertEqual(updated.verdict, "WARN")
        self.assertEqual(updated.overallScore, 0.82)
        self.assertEqual(updated.caseCount, 2)
        self.assertEqual(updated.completedAt, CLOCK)

    def testUpdatingAnUnknownRunIsRefused(self) -> None:
        with self.assertRaises(AIEvaluationInvalid):
            self.store.updateRun(self.makeRun())

    def testRunsAreTenantScoped(self) -> None:
        stored = self.store.saveRun(self.makeRun())
        self.assertIsNone(self.store.getRun(self.otherTenantId, stored.id))
        self.assertEqual(self.store.listRuns(self.otherTenantId), ())

    def testRunsAreListedNewestFirstAndFilteredBySuite(self) -> None:
        older = self.store.saveRun(self.makeRun())
        AIEvaluationRunModel.objects.filter(id=older.id).update(
            createdAt=CLOCK - timedelta(hours=1)
        )
        newer = self.store.saveRun(self.makeRun())
        self.store.saveRun(self.makeRun(suiteCode="SAFETY_GOLDEN"))
        runs = self.store.listRuns(self.tenantId, "RAG_GOLDEN")
        self.assertEqual([item.id for item in runs], [newer.id, older.id])
        self.assertEqual(len(self.store.listRuns(self.tenantId)), 3)
        self.assertEqual(len(self.store.listRuns(self.tenantId, limit=1)), 1)

    def testLatestRunOnlyConsidersCompletedRuns(self) -> None:
        pending = self.store.saveRun(self.makeRun())
        self.assertIsNone(self.store.latestRun(self.tenantId, "RAG_GOLDEN"))
        pending.transitionTo("RUNNING", now=CLOCK)
        pending.complete(
            verdict="PASS",
            overallScore=0.9,
            passedCount=1,
            warnedCount=0,
            failedCount=0,
            now=CLOCK,
        )
        self.store.updateRun(pending)
        latest = self.store.latestRun(self.tenantId, "RAG_GOLDEN")
        assert latest is not None
        self.assertEqual(latest.id, pending.id)

    def testLatestRunCanExcludeTheRunInFlight(self) -> None:
        first = self.store.saveRun(self.makeRun())
        first.transitionTo("RUNNING", now=CLOCK)
        first.complete(
            verdict="PASS",
            overallScore=0.9,
            passedCount=1,
            warnedCount=0,
            failedCount=0,
            now=CLOCK,
        )
        self.store.updateRun(first)
        current = self.store.saveRun(self.makeRun())
        latest = self.store.latestRun(self.tenantId, "RAG_GOLDEN", excludeRunId=current.id)
        assert latest is not None
        self.assertEqual(latest.id, first.id)

    def testResultsRoundTripWithMetricScoreFidelity(self) -> None:
        run = self.store.saveRun(self.makeRun())
        stored = self.store.saveResults((self.result(run.id),))
        self.assertEqual(len(stored), 1)
        loaded = self.store.listResults(self.tenantId, run.id)[0]
        self.assertEqual(loaded.verdict, "PASS")
        self.assertEqual(loaded.score, 0.91)
        self.assertEqual(len(loaded.scores), 2)
        grounded = loaded.scoreFor("GROUNDEDNESS")
        assert grounded is not None
        self.assertEqual(grounded.score, 0.95)
        self.assertEqual(grounded.detail, "ok")
        self.assertTrue(grounded.required)
        self.assertEqual(loaded.citationCount, 2)
        self.assertEqual(Decimal(loaded.cost), Decimal("0.0012"))

    def testEmptyResultWriteIsANoop(self) -> None:
        self.assertEqual(self.store.saveResults(()), ())

    def testResultsAreOrderedByCaseCode(self) -> None:
        run = self.store.saveRun(self.makeRun())
        self.store.saveResults((self.result(run.id, "ZULU"), self.result(run.id, "ALPHA")))
        codes = [item.caseCode for item in self.store.listResults(self.tenantId, run.id)]
        self.assertEqual(codes, ["ALPHA", "ZULU"])

    def testOneResultPerCasePerRunIsEnforced(self) -> None:
        run = self.store.saveRun(self.makeRun())
        self.store.saveResults((self.result(run.id),))
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.store.saveResults((self.result(run.id),))

    def testTheSameCaseMayAppearInTwoRuns(self) -> None:
        first = self.store.saveRun(self.makeRun())
        second = self.store.saveRun(self.makeRun())
        self.store.saveResults((self.result(first.id),))
        self.store.saveResults((self.result(second.id),))
        self.assertEqual(AIEvaluationResultModel.objects.count(), 2)

    def testDeletingARunCascadesToItsResults(self) -> None:
        run = self.store.saveRun(self.makeRun())
        self.store.saveResults((self.result(run.id),))
        AIEvaluationRunModel.objects.filter(id=run.id).delete()
        self.assertEqual(AIEvaluationResultModel.objects.count(), 0)

    def testRetentionSweepOnlyRemovesSettledRuns(self) -> None:
        settled = self.store.saveRun(self.makeRun())
        settled.transitionTo("RUNNING", now=CLOCK)
        settled.complete(
            verdict="PASS",
            overallScore=0.9,
            passedCount=1,
            warnedCount=0,
            failedCount=0,
            now=CLOCK,
        )
        self.store.updateRun(settled)
        inFlight = self.store.saveRun(self.makeRun())
        inFlight.transitionTo("RUNNING", now=CLOCK)
        self.store.updateRun(inFlight)
        AIEvaluationRunModel.objects.filter(id__in=[settled.id, inFlight.id]).update(
            createdAt=CLOCK - timedelta(days=800)
        )
        removed = self.store.deleteRunsBefore(self.tenantId, CLOCK - timedelta(days=30))
        self.assertEqual(removed, 1)
        self.assertTrue(AIEvaluationRunModel.objects.filter(id=inFlight.id).exists())

    def testRetentionSweepCanRunAcrossAllTenants(self) -> None:
        for tenant in (self.tenantId, self.otherTenantId):
            run = self.store.saveRun(self.makeRun(tenantId=tenant))
            run.transitionTo("RUNNING", now=CLOCK)
            run.complete(
                verdict="PASS",
                overallScore=0.9,
                passedCount=1,
                warnedCount=0,
                failedCount=0,
                now=CLOCK,
            )
            self.store.updateRun(run)
        AIEvaluationRunModel.objects.all().update(createdAt=CLOCK - timedelta(days=800))
        self.assertEqual(self.store.deleteRunsBefore(None, CLOCK - timedelta(days=30)), 2)

    def testRetentionSweepWithNothingToDoReturnsZero(self) -> None:
        self.assertEqual(self.store.deleteRunsBefore(self.tenantId, CLOCK - timedelta(days=30)), 0)

    def testMappersProduceValidatedEntities(self) -> None:
        run = self.store.saveRun(self.makeRun())
        self.store.saveResults((self.result(run.id),))
        runRow = AIEvaluationRunModel.objects.get(id=run.id)
        resultRow = AIEvaluationResultModel.objects.get(run_id=run.id)
        self.assertIsInstance(runToEntity(runRow), AIEvaluationRun)
        entity = resultToEntity(resultRow)
        self.assertIsInstance(entity, AIEvaluationResult)
        self.assertEqual(entity.runId, run.id)

    def testUnknownRunReadsAsNone(self) -> None:
        self.assertIsNone(self.store.getRun(self.tenantId, uuid.uuid4()))
