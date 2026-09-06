"""Django persistence for the Phase 13-U evaluation platform.

Row↔entity mapping only — no business rule lives here. Every read and
write is tenant-scoped, and entities are rehydrated through the domain
records so an invalid stored row can never re-enter the domain.

Metric scores are stored as a JSON list of plain mappings rather than as
rows: they are always read as a whole with their result, they are never
queried individually, and keeping them inline means a run is one insert
per case instead of one per metric.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.evaluationRecords import (
    AIEvaluationCase,
    AIEvaluationResult,
    AIEvaluationRun,
)
from apps.ai.domain.exceptions import AIEvaluationInvalid
from apps.ai.domain.valueObjects.evaluationTypes import MetricScore
from apps.ai.infrastructure.models import (
    AIEvaluationCaseModel,
    AIEvaluationResultModel,
    AIEvaluationRunModel,
)


def _scoreToDict(score: MetricScore) -> dict[str, Any]:
    return {
        "metric": score.metric,
        "score": score.score,
        "verdict": score.verdict,
        "observed": score.observed,
        "detail": score.detail,
        "weight": score.weight,
        "required": score.required,
    }


def _scoreFromDict(payload: dict[str, Any]) -> MetricScore:
    return MetricScore(
        metric=str(payload.get("metric", "")),
        score=float(payload.get("score", 0.0) or 0.0),
        verdict=str(payload.get("verdict", "PASS") or "PASS"),
        observed=payload.get("observed"),
        detail=str(payload.get("detail", "") or ""),
        weight=float(payload.get("weight", 1.0) or 1.0),
        required=bool(payload.get("required", False)),
    )


def caseToEntity(row: AIEvaluationCaseModel) -> AIEvaluationCase:
    return AIEvaluationCase(
        tenantId=row.tenantId,
        suiteCode=row.suiteCode,
        caseCode=row.caseCode,
        question=row.question,
        expectedTerms=tuple(row.expectedTerms or ()),
        forbiddenTerms=tuple(row.forbiddenTerms or ()),
        expectedSchema=dict(row.expectedSchema or {}),
        minimumCitations=row.minimumCitations,
        latencyBudgetMs=row.latencyBudgetMs,
        costBudget=str(row.costBudget),
        spaceCode=row.spaceCode or "",
        isActive=row.isActive,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
        updatedAt=row.updatedAt,
    )


def runToEntity(row: AIEvaluationRunModel) -> AIEvaluationRun:
    return AIEvaluationRun(
        tenantId=row.tenantId,
        suiteCode=row.suiteCode,
        method=row.method,
        criteriaSignature=row.criteriaSignature or "",
        status=row.status,
        verdict=row.verdict,
        caseCount=row.caseCount,
        passedCount=row.passedCount,
        warnedCount=row.warnedCount,
        failedCount=row.failedCount,
        overallScore=float(row.overallScore),
        baselineRunId=row.baselineRunId,
        errorCode=row.errorCode or "",
        startedAt=row.startedAt,
        completedAt=row.completedAt,
        triggeredBy=row.triggeredBy,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


def resultToEntity(row: AIEvaluationResultModel) -> AIEvaluationResult:
    return AIEvaluationResult(
        tenantId=row.tenantId,
        runId=row.run_id,
        caseCode=row.caseCode,
        verdict=row.verdict,
        score=float(row.score),
        scores=tuple(_scoreFromDict(item) for item in (row.scores or [])),
        latencyMs=row.latencyMs,
        totalTokens=row.totalTokens,
        cost=str(row.cost),
        citationCount=row.citationCount,
        answerFingerprint=row.answerFingerprint or "",
        errorCode=row.errorCode or "",
        notes=row.notes or "",
        requestId=row.requestId,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


class DjangoEvaluationCaseStore:
    """``EvaluationCaseStore`` over ``aiEvaluationCases``."""

    def saveCase(self, case: AIEvaluationCase) -> AIEvaluationCase:
        row = AIEvaluationCaseModel.objects.create(
            id=case.id,
            tenantId=case.tenantId,
            suiteCode=case.suiteCode,
            caseCode=case.caseCode,
            question=case.question,
            expectedTerms=list(case.expectedTerms),
            forbiddenTerms=list(case.forbiddenTerms),
            expectedSchema=dict(case.expectedSchema),
            minimumCitations=case.minimumCitations,
            latencyBudgetMs=case.latencyBudgetMs,
            costBudget=Decimal(case.costBudget),
            spaceCode=case.spaceCode,
            isActive=case.isActive,
            metadata=dict(case.metadata),
        )
        return caseToEntity(row)

    def updateCase(self, case: AIEvaluationCase) -> AIEvaluationCase:
        updated = AIEvaluationCaseModel.objects.filter(tenantId=case.tenantId, id=case.id).update(
            question=case.question,
            expectedTerms=list(case.expectedTerms),
            forbiddenTerms=list(case.forbiddenTerms),
            expectedSchema=dict(case.expectedSchema),
            minimumCitations=case.minimumCitations,
            latencyBudgetMs=case.latencyBudgetMs,
            costBudget=Decimal(case.costBudget),
            spaceCode=case.spaceCode,
            isActive=case.isActive,
            metadata=dict(case.metadata),
        )
        if not updated:
            raise AIEvaluationInvalid("Evaluation case row was not found for update.")
        return caseToEntity(AIEvaluationCaseModel.objects.get(tenantId=case.tenantId, id=case.id))

    def getCase(self, tenantId: uuid.UUID, caseId: uuid.UUID) -> AIEvaluationCase | None:
        row = AIEvaluationCaseModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id=requireUuid(caseId, "caseId")
        ).first()
        return None if row is None else caseToEntity(row)

    def findCase(
        self, tenantId: uuid.UUID, suiteCode: str, caseCode: str
    ) -> AIEvaluationCase | None:
        row = AIEvaluationCaseModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            suiteCode=str(suiteCode).strip().upper(),
            caseCode=str(caseCode).strip().upper(),
        ).first()
        return None if row is None else caseToEntity(row)

    def listCases(
        self, tenantId: uuid.UUID, suiteCode: str = "", *, activeOnly: bool = True
    ) -> tuple[AIEvaluationCase, ...]:
        query = AIEvaluationCaseModel.objects.filter(tenantId=requireUuid(tenantId, "tenantId"))
        if suiteCode:
            query = query.filter(suiteCode=str(suiteCode).strip().upper())
        if activeOnly:
            query = query.filter(isActive=True)
        return tuple(caseToEntity(row) for row in query.order_by("suiteCode", "caseCode"))

    def listSuites(self, tenantId: uuid.UUID) -> tuple[str, ...]:
        rows = (
            AIEvaluationCaseModel.objects.filter(tenantId=requireUuid(tenantId, "tenantId"))
            .values_list("suiteCode", flat=True)
            .distinct()
            .order_by("suiteCode")
        )
        return tuple(rows)

    def deleteCase(self, tenantId: uuid.UUID, caseId: uuid.UUID) -> int:
        removed, _ = AIEvaluationCaseModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id=requireUuid(caseId, "caseId")
        ).delete()
        return int(removed)


class DjangoEvaluationRunStore:
    """``EvaluationRunStore`` over ``aiEvaluationRuns``/``aiEvaluationResults``."""

    def saveRun(self, run: AIEvaluationRun) -> AIEvaluationRun:
        row = AIEvaluationRunModel.objects.create(
            id=run.id,
            tenantId=run.tenantId,
            suiteCode=run.suiteCode,
            method=run.method,
            criteriaSignature=run.criteriaSignature,
            status=run.status,
            verdict=run.verdict,
            caseCount=run.caseCount,
            passedCount=run.passedCount,
            warnedCount=run.warnedCount,
            failedCount=run.failedCount,
            overallScore=Decimal(str(run.overallScore)),
            baselineRunId=run.baselineRunId,
            triggeredBy=run.triggeredBy,
            errorCode=run.errorCode,
            startedAt=run.startedAt,
            completedAt=run.completedAt,
            metadata=dict(run.metadata),
        )
        return runToEntity(row)

    def updateRun(self, run: AIEvaluationRun) -> AIEvaluationRun:
        updated = AIEvaluationRunModel.objects.filter(tenantId=run.tenantId, id=run.id).update(
            status=run.status,
            verdict=run.verdict,
            caseCount=run.caseCount,
            passedCount=run.passedCount,
            warnedCount=run.warnedCount,
            failedCount=run.failedCount,
            overallScore=Decimal(str(run.overallScore)),
            errorCode=run.errorCode,
            startedAt=run.startedAt,
            completedAt=run.completedAt,
            metadata=dict(run.metadata),
        )
        if not updated:
            raise AIEvaluationInvalid("Evaluation run row was not found for update.")
        return runToEntity(AIEvaluationRunModel.objects.get(tenantId=run.tenantId, id=run.id))

    def getRun(self, tenantId: uuid.UUID, runId: uuid.UUID) -> AIEvaluationRun | None:
        row = AIEvaluationRunModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id=requireUuid(runId, "runId")
        ).first()
        return None if row is None else runToEntity(row)

    def listRuns(
        self, tenantId: uuid.UUID, suiteCode: str = "", *, limit: int = 50
    ) -> tuple[AIEvaluationRun, ...]:
        query = AIEvaluationRunModel.objects.filter(tenantId=requireUuid(tenantId, "tenantId"))
        if suiteCode:
            query = query.filter(suiteCode=str(suiteCode).strip().upper())
        rows = query.order_by("-createdAt", "-id")[: max(1, int(limit))]
        return tuple(runToEntity(row) for row in rows)

    def latestRun(
        self, tenantId: uuid.UUID, suiteCode: str, *, excludeRunId: uuid.UUID | None = None
    ) -> AIEvaluationRun | None:
        query = AIEvaluationRunModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            suiteCode=str(suiteCode).strip().upper(),
            status="COMPLETED",
        )
        if excludeRunId is not None:
            query = query.exclude(id=requireUuid(excludeRunId, "excludeRunId"))
        row = query.order_by("-completedAt", "-createdAt").first()
        return None if row is None else runToEntity(row)

    def saveResults(
        self, results: tuple[AIEvaluationResult, ...]
    ) -> tuple[AIEvaluationResult, ...]:
        if not results:
            return ()
        rows = [
            AIEvaluationResultModel(
                id=result.id,
                tenantId=result.tenantId,
                run_id=result.runId,
                caseCode=result.caseCode,
                verdict=result.verdict,
                score=Decimal(str(result.score)),
                scores=[_scoreToDict(item) for item in result.scores],
                latencyMs=result.latencyMs,
                totalTokens=result.totalTokens,
                cost=Decimal(result.cost),
                citationCount=result.citationCount,
                answerFingerprint=result.answerFingerprint,
                requestId=result.requestId,
                errorCode=result.errorCode,
                notes=result.notes,
                metadata=dict(result.metadata),
            )
            for result in results
        ]
        with transaction.atomic():
            AIEvaluationResultModel.objects.bulk_create(rows)
        stored = AIEvaluationResultModel.objects.filter(
            id__in=[result.id for result in results]
        ).order_by("caseCode")
        return tuple(resultToEntity(row) for row in stored)

    def listResults(self, tenantId: uuid.UUID, runId: uuid.UUID) -> tuple[AIEvaluationResult, ...]:
        rows = AIEvaluationResultModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), run_id=requireUuid(runId, "runId")
        ).order_by("caseCode")
        return tuple(resultToEntity(row) for row in rows)

    def deleteRunsBefore(self, tenantId: uuid.UUID | None, cutoff: datetime) -> int:
        """Purge settled runs only; a run in flight is never swept away."""

        query = AIEvaluationRunModel.objects.filter(
            createdAt__lt=cutoff, status__in=("COMPLETED", "FAILED", "CANCELLED")
        )
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        identifiers = list(query.values_list("id", flat=True))
        if not identifiers:
            return 0
        AIEvaluationRunModel.objects.filter(id__in=identifiers).delete()
        return len(identifiers)


__all__ = [
    "DjangoEvaluationCaseStore",
    "DjangoEvaluationRunStore",
    "caseToEntity",
    "resultToEntity",
    "runToEntity",
]
