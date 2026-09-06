"""Evaluation entities for Phase 13-U.

Three records make quality measurable and comparable over time:

- ``AIEvaluationCase`` — one golden case: the input, what a good answer
  must contain, and the budgets it must respect. Cases are tenant-scoped
  and versioned by suite, so "the bar" is data, not code;
- ``AIEvaluationRun`` — one execution of a suite under one criteria
  signature, with its lifecycle and aggregate verdict;
- ``AIEvaluationResult`` — what happened to one case inside one run:
  every metric score, the verdict, and the observed cost/latency.

Pure dataclasses: no Django, ORM, HTTP, provider SDK, queue, or network
dependency. ``AIEvaluationResult.toDomainEvaluation`` bridges to the
Phase 13-B ``AIEvaluation`` primitive.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import AIEvaluation, newId, requireUuid, utcNow
from apps.ai.domain.valueObjects.evaluationTypes import (
    MAX_SUITE_CODE_LENGTH,
    EvaluationCriteria,
    MetricScore,
    clampScore,
    ensureEvaluationMethod,
    ensureRunStatus,
    ensureVerdict,
    weightedAverage,
    worstVerdict,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_.-]{0,79}$")

#: Lifecycle transitions of a run (§U.7).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"RUNNING", "CANCELLED"},
    "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "CANCELLED": set(),
}


def ensureCode(value: str, fieldName: str = "code") -> str:
    normalized = str(value or "").strip().upper().replace(" ", "_")
    if not _CODE_PATTERN.fullmatch(normalized) or len(normalized) > MAX_SUITE_CODE_LENGTH:
        raise ValidationFailedError(
            "Evaluation codes must be uppercase identifiers.",
            fieldErrors={fieldName: normalized[:40]},
        )
    return normalized


@dataclass
class AIEvaluationCase:
    """One golden case: the input plus what a good answer must satisfy."""

    tenantId: uuid.UUID
    suiteCode: str
    caseCode: str
    question: str
    expectedTerms: tuple[str, ...] = ()
    forbiddenTerms: tuple[str, ...] = ()
    expectedSchema: dict[str, Any] = field(default_factory=dict)
    minimumCitations: int = 0
    latencyBudgetMs: int = 0
    costBudget: str = "0"
    spaceCode: str = ""
    isActive: bool = True
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.suiteCode = ensureCode(self.suiteCode, "suiteCode")
        self.caseCode = ensureCode(self.caseCode, "caseCode")
        self.question = str(self.question or "").strip()
        if not self.question:
            raise ValidationFailedError("Evaluation case question is required.")
        self.expectedTerms = tuple(
            str(term).strip() for term in self.expectedTerms if str(term).strip()
        )
        self.forbiddenTerms = tuple(
            str(term).strip().casefold() for term in self.forbiddenTerms if str(term).strip()
        )
        if not isinstance(self.expectedSchema, dict):
            raise ValidationFailedError("Evaluation case schema must be a mapping.")
        for name in ("minimumCitations", "latencyBudgetMs"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationFailedError(
                    "Evaluation budgets must be non-negative integers.",
                    fieldErrors={name: str(value)},
                )
        self.costBudget = str(self.costBudget or "0")
        self.spaceCode = str(self.spaceCode or "").strip().upper()
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Evaluation case metadata must be a mapping.")

    @property
    def qualifiedCode(self) -> str:
        return f"{self.suiteCode}:{self.caseCode}"

    @property
    def expectsStructuredOutput(self) -> bool:
        return bool(self.expectedSchema)

    def deactivate(self, *, now: datetime | None = None) -> None:
        self.isActive = False
        self.updatedAt = now or utcNow()

    def activate(self, *, now: datetime | None = None) -> None:
        self.isActive = True
        self.updatedAt = now or utcNow()


@dataclass
class AIEvaluationRun:
    """One execution of one suite under one criteria signature (§U.7)."""

    tenantId: uuid.UUID
    suiteCode: str
    method: str = "AUTOMATIC"
    criteriaSignature: str = ""
    status: str = "PENDING"
    verdict: str = "PASS"
    caseCount: int = 0
    passedCount: int = 0
    warnedCount: int = 0
    failedCount: int = 0
    overallScore: float = 0.0
    baselineRunId: uuid.UUID | None = None
    errorCode: str = ""
    startedAt: datetime | None = None
    completedAt: datetime | None = None
    triggeredBy: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.suiteCode = ensureCode(self.suiteCode, "suiteCode")
        self.method = ensureEvaluationMethod(self.method)
        self.status = ensureRunStatus(self.status)
        self.verdict = ensureVerdict(self.verdict)
        self.criteriaSignature = str(self.criteriaSignature or "").strip()
        self.errorCode = str(self.errorCode or "").strip().upper()
        if self.baselineRunId is not None:
            self.baselineRunId = requireUuid(self.baselineRunId, "baselineRunId")
        if self.triggeredBy is not None:
            self.triggeredBy = requireUuid(self.triggeredBy, "triggeredBy")
        for name in ("caseCount", "passedCount", "warnedCount", "failedCount"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationFailedError(
                    "Evaluation counters must be non-negative integers.",
                    fieldErrors={name: str(value)},
                )
        self.overallScore = clampScore(self.overallScore)
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Evaluation run metadata must be a mapping.")

    @property
    def isTerminal(self) -> bool:
        return self.status in ("COMPLETED", "FAILED", "CANCELLED")

    @property
    def passRate(self) -> float:
        if not self.caseCount:
            return 0.0
        return round(self.passedCount / self.caseCount, 6)

    def transitionTo(self, status: str, *, now: datetime | None = None) -> None:
        target = ensureRunStatus(status)
        if target != self.status and target not in _ALLOWED_TRANSITIONS[self.status]:
            raise ValidationFailedError(
                f"Invalid evaluation run transition {self.status} → {target}.",
                fieldErrors={"status": target},
            )
        moment = now or utcNow()
        if target == "RUNNING" and self.startedAt is None:
            self.startedAt = moment
        if target in ("COMPLETED", "FAILED", "CANCELLED"):
            self.completedAt = moment
        self.status = target

    def complete(
        self,
        *,
        verdict: str,
        overallScore: float,
        passedCount: int,
        warnedCount: int,
        failedCount: int,
        now: datetime | None = None,
    ) -> None:
        self.transitionTo("COMPLETED", now=now)
        self.verdict = ensureVerdict(verdict)
        self.overallScore = clampScore(overallScore)
        self.passedCount = passedCount
        self.warnedCount = warnedCount
        self.failedCount = failedCount
        self.caseCount = passedCount + warnedCount + failedCount
        self.errorCode = ""

    def fail(self, errorCode: str, *, now: datetime | None = None) -> None:
        self.transitionTo("FAILED", now=now)
        self.verdict = "FAIL"
        self.errorCode = str(errorCode or "AI_EVALUATION_FAILED").strip().upper()


@dataclass
class AIEvaluationResult:
    """The outcome of one case inside one run (§U.8)."""

    tenantId: uuid.UUID
    runId: uuid.UUID
    caseCode: str
    verdict: str = "PASS"
    score: float = 0.0
    scores: tuple[MetricScore, ...] = ()
    latencyMs: int = 0
    totalTokens: int = 0
    cost: str = "0"
    citationCount: int = 0
    answerFingerprint: str = ""
    errorCode: str = ""
    notes: str = ""
    requestId: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.runId = requireUuid(self.runId, "runId")
        self.id = requireUuid(self.id, "id")
        if self.requestId is not None:
            self.requestId = requireUuid(self.requestId, "requestId")
        self.caseCode = ensureCode(self.caseCode, "caseCode")
        self.verdict = ensureVerdict(self.verdict)
        self.score = clampScore(self.score)
        for item in self.scores:
            if not isinstance(item, MetricScore):
                raise ValidationFailedError("Evaluation results require MetricScore values.")
        for name in ("latencyMs", "totalTokens", "citationCount"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValidationFailedError(
                    "Evaluation measurements must be non-negative integers.",
                    fieldErrors={name: str(value)},
                )
        self.cost = str(self.cost or "0")
        self.errorCode = str(self.errorCode or "").strip().upper()
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Evaluation result metadata must be a mapping.")

    def scoreFor(self, metric: str) -> MetricScore | None:
        for item in self.scores:
            if item.metric == metric.strip().upper():
                return item
        return None

    def failedMetrics(self) -> tuple[str, ...]:
        return tuple(item.metric for item in self.scores if item.verdict == "FAIL")

    def metricMap(self) -> dict[str, float]:
        return {item.metric: item.score for item in self.scores}

    def recomputeVerdict(self, criteria: EvaluationCriteria) -> None:
        """Recompute the aggregate verdict and score from the metric scores."""

        if not self.scores:
            self.verdict = "FAIL"
            self.score = 0.0
            return
        missing = [metric for metric in criteria.requiredMetrics if self.scoreFor(metric) is None]
        verdicts = [item.verdict for item in self.scores]
        if missing:
            verdicts.append("FAIL")
        self.verdict = worstVerdict(verdicts)
        self.score = clampScore(weightedAverage(self.metricMap(), criteria.weights()))

    def toDomainEvaluation(self, *, method: str = "AUTOMATIC") -> AIEvaluation:
        """Bridge to the Phase 13-B ``AIEvaluation`` primitive."""

        if self.requestId is None:
            raise ValidationFailedError(
                "An evaluation result without requestId cannot be bridged to AIEvaluation."
            )
        return AIEvaluation(
            tenantId=self.tenantId,
            requestId=self.requestId,
            method=method,
            id=self.id,
            metrics=self.metricMap(),
            notes=self.notes,
            createdAt=self.createdAt,
        )


__all__ = [
    "AIEvaluationCase",
    "AIEvaluationResult",
    "AIEvaluationRun",
    "ensureCode",
]
