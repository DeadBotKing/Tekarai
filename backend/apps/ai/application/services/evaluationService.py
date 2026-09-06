"""Application orchestration for the Phase 13-U evaluation platform.

``EvaluationApplicationService`` runs a suite of golden cases against
whatever is under test, scores every case with the pure engine, judges it
against ``EvaluationCriteria``, aggregates a run verdict, and compares the
run to its predecessor to catch quality regressions.

Behaviour worth stating once:

- **Acceptance is data.** The bar lives in ``EvaluationCriteria`` (per
  metric thresholds, weights, required metrics, run-level limits) and its
  signature is stamped on every run, so two runs are only ever compared
  under the same bar (Open Question #9, closed).
- **Offline by construction.** Scoring never calls a model. Whatever
  produced the answer is injected as an ``AnswerProducer``; the grading
  itself is closed-form and reproducible.
- **A broken case fails that case, not the run.** An exception from the
  producer is recorded as a failed result with its error code; the suite
  keeps going and the run still reports a verdict.
- **Runs are history.** They are never edited after settling, which is
  what makes "was this change worse?" answerable at all.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.evaluationRecords import (
    AIEvaluationCase,
    AIEvaluationResult,
    AIEvaluationRun,
    ensureCode,
)
from apps.ai.domain.evaluationPorts import (
    AnswerProducer,
    EvaluationAuditLogger,
    EvaluationCaseStore,
    EvaluationRunStore,
)
from apps.ai.domain.exceptions import (
    AIConfigurationError,
    AIEvaluationCaseAlreadyRegistered,
    AIEvaluationCaseNotFound,
    AIEvaluationCriteriaInvalid,
    AIEvaluationInvalid,
    AIEvaluationRunNotFound,
)
from apps.ai.domain.services.evaluationEngine import (
    CaseObservation,
    EvaluationEngine,
    EvaluationJudge,
    RegressionReport,
    RunAggregator,
    RunSummary,
    compareRuns,
)
from apps.ai.domain.valueObjects.evaluationTypes import (
    MAX_CASES_PER_SUITE,
    EvaluationCriteria,
    MetricThreshold,
    ensureEvaluationMethod,
    ensureMetric,
)

#: Audit actions appended by U (registered in the Phase 13-O vocabulary).
AUDIT_EVALUATION_STARTED = "EVALUATION_STARTED"
AUDIT_EVALUATION_COMPLETED = "EVALUATION_COMPLETED"
AUDIT_EVALUATION_FAILED = "EVALUATION_FAILED"
AUDIT_EVALUATION_REGRESSED = "EVALUATION_REGRESSED"


@dataclass(frozen=True)
class EvaluationSettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    minimumOverallScore: float = 0.7
    maximumFailedCases: int = 0
    maximumWarnRatio: float = 0.3
    regressionTolerance: float = 0.02
    groundednessFailBelow: float = 0.5
    groundednessWarnBelow: float = 0.75
    maxCasesPerRun: int = 200
    retentionDays: int = 365
    forbiddenTerms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.maxCasesPerRun < 1 or self.maxCasesPerRun > MAX_CASES_PER_SUITE:
            raise AIConfigurationError("aiEvaluationMaxCasesPerRun is out of range.")
        if self.retentionDays < 1:
            raise AIConfigurationError("aiEvaluationRetentionDays must be positive.")
        # Building the criteria here means an impossible configuration fails
        # at construction, not on the first run.
        self.criteria()

    def criteria(self) -> EvaluationCriteria:
        """Platform criteria narrowed by configuration (§U.5)."""

        platform = EvaluationCriteria.platformDefault()
        thresholds = []
        for threshold in platform.thresholds:
            if threshold.metric == "GROUNDEDNESS":
                thresholds.append(
                    MetricThreshold(
                        metric="GROUNDEDNESS",
                        failBelow=self.groundednessFailBelow,
                        warnBelow=max(self.groundednessWarnBelow, self.groundednessFailBelow),
                        weight=threshold.weight,
                        required=True,
                    )
                )
            else:
                thresholds.append(threshold)
        return EvaluationCriteria(
            thresholds=tuple(thresholds),
            minimumOverallScore=self.minimumOverallScore,
            maximumFailedCases=self.maximumFailedCases,
            maximumWarnRatio=self.maximumWarnRatio,
            regressionTolerance=self.regressionTolerance,
        )

    @classmethod
    def fromDjangoSettings(cls) -> EvaluationSettings:
        rawTerms = str(getattr(djangoSettings, "AI_EVALUATION_FORBIDDEN_TERMS", "") or "")
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_EVALUATION_ENABLED", True)),
            minimumOverallScore=float(
                getattr(djangoSettings, "AI_EVALUATION_MIN_OVERALL_SCORE", 0.7) or 0.7
            ),
            maximumFailedCases=int(
                getattr(djangoSettings, "AI_EVALUATION_MAX_FAILED_CASES", 0) or 0
            ),
            maximumWarnRatio=float(
                getattr(djangoSettings, "AI_EVALUATION_MAX_WARN_RATIO", 0.3) or 0.3
            ),
            regressionTolerance=float(
                getattr(djangoSettings, "AI_EVALUATION_REGRESSION_TOLERANCE", 0.02) or 0.02
            ),
            groundednessFailBelow=float(
                getattr(djangoSettings, "AI_EVALUATION_GROUNDEDNESS_FAIL_BELOW", 0.5) or 0.5
            ),
            groundednessWarnBelow=float(
                getattr(djangoSettings, "AI_EVALUATION_GROUNDEDNESS_WARN_BELOW", 0.75) or 0.75
            ),
            maxCasesPerRun=int(
                getattr(djangoSettings, "AI_EVALUATION_MAX_CASES_PER_RUN", 200) or 200
            ),
            retentionDays=int(getattr(djangoSettings, "AI_EVALUATION_RETENTION_DAYS", 365) or 365),
            forbiddenTerms=tuple(term.strip() for term in rawTerms.split(",") if term.strip()),
        )


@dataclass(frozen=True)
class RegisterCaseCommand:
    """Add or replace one golden case (§U.4)."""

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
    metadata: dict[str, Any] = field(default_factory=dict)
    replace: bool = False


@dataclass(frozen=True)
class RunSuiteCommand:
    """Execute one suite against the injected producer (§U.6)."""

    suiteCode: str
    method: str = "AUTOMATIC"
    criteria: EvaluationCriteria | None = None
    metrics: tuple[str, ...] = ()
    caseCodes: tuple[str, ...] = ()
    baselineRunId: uuid.UUID | None = None
    compareToPrevious: bool = True
    triggeredBy: uuid.UUID | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaseDescriptor:
    """Safe read model of one golden case."""

    caseId: uuid.UUID
    suiteCode: str
    caseCode: str
    qualifiedCode: str
    question: str
    expectedTerms: tuple[str, ...]
    minimumCitations: int
    latencyBudgetMs: int
    costBudget: str
    spaceCode: str
    isActive: bool
    createdAt: datetime

    @classmethod
    def of(cls, case: AIEvaluationCase) -> CaseDescriptor:
        return cls(
            caseId=case.id,
            suiteCode=case.suiteCode,
            caseCode=case.caseCode,
            qualifiedCode=case.qualifiedCode,
            question=case.question,
            expectedTerms=case.expectedTerms,
            minimumCitations=case.minimumCitations,
            latencyBudgetMs=case.latencyBudgetMs,
            costBudget=case.costBudget,
            spaceCode=case.spaceCode,
            isActive=case.isActive,
            createdAt=case.createdAt,
        )


@dataclass(frozen=True)
class ResultDescriptor:
    """Safe read model of one case outcome."""

    resultId: uuid.UUID
    caseCode: str
    verdict: str
    score: float
    metrics: dict[str, float]
    failedMetrics: tuple[str, ...]
    latencyMs: int
    citationCount: int
    errorCode: str
    notes: str

    @classmethod
    def of(cls, result: AIEvaluationResult) -> ResultDescriptor:
        return cls(
            resultId=result.id,
            caseCode=result.caseCode,
            verdict=result.verdict,
            score=result.score,
            metrics=result.metricMap(),
            failedMetrics=result.failedMetrics(),
            latencyMs=result.latencyMs,
            citationCount=result.citationCount,
            errorCode=result.errorCode,
            notes=result.notes,
        )


@dataclass(frozen=True)
class RunDescriptor:
    """Safe read model of one run."""

    runId: uuid.UUID
    tenantId: uuid.UUID
    suiteCode: str
    method: str
    status: str
    verdict: str
    overallScore: float
    caseCount: int
    passedCount: int
    warnedCount: int
    failedCount: int
    criteriaSignature: str
    baselineRunId: uuid.UUID | None
    errorCode: str
    startedAt: datetime | None
    completedAt: datetime | None

    @classmethod
    def of(cls, run: AIEvaluationRun) -> RunDescriptor:
        return cls(
            runId=run.id,
            tenantId=run.tenantId,
            suiteCode=run.suiteCode,
            method=run.method,
            status=run.status,
            verdict=run.verdict,
            overallScore=run.overallScore,
            caseCount=run.caseCount,
            passedCount=run.passedCount,
            warnedCount=run.warnedCount,
            failedCount=run.failedCount,
            criteriaSignature=run.criteriaSignature,
            baselineRunId=run.baselineRunId,
            errorCode=run.errorCode,
            startedAt=run.startedAt,
            completedAt=run.completedAt,
        )


@dataclass(frozen=True)
class RunReport:
    """Everything one run produced (§U.9)."""

    run: RunDescriptor
    summary: RunSummary
    results: tuple[ResultDescriptor, ...]
    regression: RegressionReport | None = None

    @property
    def accepted(self) -> bool:
        return self.run.verdict != "FAIL" and not (
            self.regression is not None and self.regression.regressed
        )


class EvaluationApplicationService:
    """Tenant-scoped facade for golden cases, runs, and regressions."""

    def __init__(
        self,
        caseStore: EvaluationCaseStore,
        runStore: EvaluationRunStore,
        *,
        producer: AnswerProducer | None = None,
        settings: EvaluationSettings | None = None,
        auditLogger: EvaluationAuditLogger | None = None,
        engine: EvaluationEngine | None = None,
        judge: EvaluationJudge | None = None,
        aggregator: RunAggregator | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.caseStore = caseStore
        self.runStore = runStore
        self.producer = producer
        self.settings = settings or EvaluationSettings()
        self.auditLogger = auditLogger
        self.engine = engine or EvaluationEngine(forbiddenTerms=self.settings.forbiddenTerms)
        self.judge = judge or EvaluationJudge()
        self.aggregator = aggregator or RunAggregator()
        self._now = now

    # ------------------------------------------------------------------
    # Golden cases (§U.4)
    # ------------------------------------------------------------------
    def registerCase(
        self, tenantId: uuid.UUID | str, command: RegisterCaseCommand
    ) -> CaseDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, RegisterCaseCommand):
            raise AIEvaluationInvalid("Registering requires a RegisterCaseCommand.")
        suite = ensureCode(command.suiteCode, "suiteCode")
        code = ensureCode(command.caseCode, "caseCode")
        existing = self.caseStore.findCase(tenant, suite, code)
        moment = self._now()
        if existing is not None and not command.replace:
            raise AIEvaluationCaseAlreadyRegistered(f"{suite}:{code}")
        if len(self.caseStore.listCases(tenant, suite)) >= MAX_CASES_PER_SUITE:
            raise AIEvaluationInvalid("Suite exceeds the platform case ceiling.")
        case = AIEvaluationCase(
            tenantId=tenant,
            suiteCode=suite,
            caseCode=code,
            question=command.question,
            expectedTerms=command.expectedTerms,
            forbiddenTerms=command.forbiddenTerms,
            expectedSchema=dict(command.expectedSchema),
            minimumCitations=command.minimumCitations,
            latencyBudgetMs=command.latencyBudgetMs,
            costBudget=command.costBudget,
            spaceCode=command.spaceCode,
            metadata=dict(command.metadata),
            id=existing.id if existing is not None else uuid.uuid4(),
            createdAt=existing.createdAt if existing is not None else moment,
            updatedAt=moment,
        )
        stored = (
            self.caseStore.updateCase(case)
            if existing is not None
            else self.caseStore.saveCase(case)
        )
        return CaseDescriptor.of(stored)

    def describeCase(
        self, tenantId: uuid.UUID | str, suiteCode: str, caseCode: str
    ) -> CaseDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        case = self.caseStore.findCase(
            tenant, ensureCode(suiteCode, "suiteCode"), ensureCode(caseCode, "caseCode")
        )
        if case is None:
            raise AIEvaluationCaseNotFound(f"{suiteCode}:{caseCode}")
        return CaseDescriptor.of(case)

    def listCases(
        self, tenantId: uuid.UUID | str, suiteCode: str = "", *, activeOnly: bool = True
    ) -> tuple[CaseDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        suite = ensureCode(suiteCode, "suiteCode") if suiteCode else ""
        cases = self.caseStore.listCases(tenant, suite, activeOnly=activeOnly)
        return tuple(CaseDescriptor.of(case) for case in cases)

    def listSuites(self, tenantId: uuid.UUID | str) -> tuple[str, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        return self.caseStore.listSuites(tenant)

    def deactivateCase(
        self, tenantId: uuid.UUID | str, suiteCode: str, caseCode: str
    ) -> CaseDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        case = self._requireCase(tenant, suiteCode, caseCode)
        case.deactivate(now=self._now())
        return CaseDescriptor.of(self.caseStore.updateCase(case))

    # ------------------------------------------------------------------
    # Runs (§U.6–§U.10)
    # ------------------------------------------------------------------
    def runSuite(self, tenantId: uuid.UUID | str, command: RunSuiteCommand) -> RunReport:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if not isinstance(command, RunSuiteCommand):
            raise AIEvaluationInvalid("Running requires a RunSuiteCommand.")
        if self.producer is None:
            raise AIConfigurationError("No answer producer is configured.")
        criteria = command.criteria or self.settings.criteria()
        if not isinstance(criteria, EvaluationCriteria):
            raise AIEvaluationCriteriaInvalid("Criteria must be an EvaluationCriteria.")
        suite = ensureCode(command.suiteCode, "suiteCode")
        metrics = tuple(ensureMetric(metric) for metric in command.metrics)

        cases = [
            case
            for case in self.caseStore.listCases(tenant, suite, activeOnly=True)
            if not command.caseCodes
            or case.caseCode in {ensureCode(code, "caseCode") for code in command.caseCodes}
        ]
        if not cases:
            raise AIEvaluationInvalid("The suite has no active case to run.")
        if len(cases) > self.settings.maxCasesPerRun:
            raise AIEvaluationInvalid("The suite exceeds the configured run ceiling.")

        moment = self._now()
        run = AIEvaluationRun(
            tenantId=tenant,
            suiteCode=suite,
            method=ensureEvaluationMethod(command.method),
            criteriaSignature=criteria.signature(),
            baselineRunId=command.baselineRunId,
            triggeredBy=command.triggeredBy,
            metadata=dict(command.metadata),
            createdAt=moment,
        )
        run.transitionTo("RUNNING", now=moment)
        run = self.runStore.saveRun(run)
        self._audit(
            tenant,
            AUDIT_EVALUATION_STARTED,
            outcome="RECORDED",
            actorId=command.triggeredBy,
            contextSources=(suite,),
            detail={"cases": len(cases), "criteria": criteria.signature()},
        )

        try:
            results = tuple(self._runCase(tenant, run, case, criteria, metrics) for case in cases)
            stored = self.runStore.saveResults(results)
            summary = self.aggregator.aggregate(stored, criteria)
            run.complete(
                verdict=summary.verdict,
                overallScore=summary.overallScore,
                passedCount=summary.passedCount,
                warnedCount=summary.warnedCount,
                failedCount=summary.failedCount,
                now=self._now(),
            )
            run = self.runStore.updateRun(run)
        except Exception as error:  # noqa: BLE001 - re-raised after bookkeeping
            run.fail(getattr(error, "code", "AI_EVALUATION_FAILED"), now=self._now())
            self.runStore.updateRun(run)
            self._audit(
                tenant,
                AUDIT_EVALUATION_FAILED,
                outcome="FAILED",
                errorCode=str(getattr(error, "code", "AI_EVALUATION_FAILED")),
                contextSources=(suite,),
                detail={"reason": str(error)[:200]},
            )
            raise

        regression = self._compareToBaseline(tenant, run, summary, criteria, command)
        self._audit(
            tenant,
            AUDIT_EVALUATION_COMPLETED,
            outcome="ALLOWED" if summary.verdict != "FAIL" else "DENIED",
            actorId=command.triggeredBy,
            contextSources=(suite,),
            detail={
                "verdict": summary.verdict,
                "score": summary.overallScore,
                "passed": summary.passedCount,
                "warned": summary.warnedCount,
                "failed": summary.failedCount,
                "reason": summary.reason,
            },
        )
        if regression is not None and regression.regressed:
            self._audit(
                tenant,
                AUDIT_EVALUATION_REGRESSED,
                outcome="DENIED",
                contextSources=(suite,),
                detail={
                    "overallDelta": regression.overallDelta,
                    "tolerance": regression.tolerance,
                    "regressedMetrics": list(regression.regressedMetrics),
                    "newFailures": list(regression.newFailures),
                    "reason": regression.reason,
                },
            )
        return RunReport(
            run=RunDescriptor.of(run),
            summary=summary,
            results=tuple(ResultDescriptor.of(item) for item in stored),
            regression=regression,
        )

    def describeRun(self, tenantId: uuid.UUID | str, runId: uuid.UUID | str) -> RunDescriptor:
        return RunDescriptor.of(self._requireRun(requireUuid(tenantId, "tenantId"), runId))

    def listRuns(
        self, tenantId: uuid.UUID | str, suiteCode: str = "", *, limit: int = 50
    ) -> tuple[RunDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        suite = ensureCode(suiteCode, "suiteCode") if suiteCode else ""
        return tuple(
            RunDescriptor.of(run) for run in self.runStore.listRuns(tenant, suite, limit=limit)
        )

    def listResults(
        self, tenantId: uuid.UUID | str, runId: uuid.UUID | str
    ) -> tuple[ResultDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        run = self._requireRun(tenant, runId)
        return tuple(
            ResultDescriptor.of(item) for item in self.runStore.listResults(tenant, run.id)
        )

    def compareRunPair(
        self,
        tenantId: uuid.UUID | str,
        baselineRunId: uuid.UUID | str,
        candidateRunId: uuid.UUID | str,
        *,
        criteria: EvaluationCriteria | None = None,
    ) -> RegressionReport:
        """Compare two settled runs; both must share the criteria signature."""

        tenant = requireUuid(tenantId, "tenantId")
        baseline = self._requireRun(tenant, baselineRunId)
        candidate = self._requireRun(tenant, candidateRunId)
        chosen = criteria or self.settings.criteria()
        if baseline.criteriaSignature != candidate.criteriaSignature:
            raise AIEvaluationCriteriaInvalid(
                "Runs graded under different criteria cannot be compared."
            )
        return compareRuns(
            self._summaryOf(tenant, baseline, chosen),
            self._summaryOf(tenant, candidate, chosen),
            chosen,
            baselineFailures=self._failedCaseCodes(tenant, baseline),
            candidateFailures=self._failedCaseCodes(tenant, candidate),
        )

    def purgeEvaluationRetention(
        self,
        tenantId: uuid.UUID | str | None = None,
        *,
        retentionDays: int | None = None,
        now: datetime | None = None,
    ) -> int:
        self._requireEnabled()
        tenant = None if tenantId is None else requireUuid(tenantId, "tenantId")
        days = self.settings.retentionDays if retentionDays is None else int(retentionDays)
        if days < 1:
            raise AIConfigurationError("Evaluation retention must be at least one day.")
        cutoff = (now or self._now()) - timedelta(days=days)
        return self.runStore.deleteRunsBefore(tenant, cutoff)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _runCase(
        self,
        tenant: uuid.UUID,
        run: AIEvaluationRun,
        case: AIEvaluationCase,
        criteria: EvaluationCriteria,
        metrics: tuple[str, ...],
    ) -> AIEvaluationResult:
        assert self.producer is not None
        try:
            observation = self.producer.produce(tenant, case)
        except Exception as error:  # noqa: BLE001 - one broken case, not a broken run
            return AIEvaluationResult(
                tenantId=tenant,
                runId=run.id,
                caseCode=case.caseCode,
                verdict="FAIL",
                score=0.0,
                errorCode=str(getattr(error, "code", "AI_EVALUATION_FAILED")),
                notes=str(error)[:300],
                createdAt=self._now(),
            )
        if not isinstance(observation, CaseObservation):
            raise AIEvaluationInvalid("The producer must return a CaseObservation.")
        if observation.failed:
            return AIEvaluationResult(
                tenantId=tenant,
                runId=run.id,
                caseCode=case.caseCode,
                verdict="FAIL",
                score=0.0,
                errorCode=observation.errorCode,
                notes="The subject under test reported an error.",
                latencyMs=observation.latencyMs,
                requestId=observation.requestId,
                createdAt=self._now(),
            )

        scores = self.engine.scoreCase(case, observation, criteria, metrics=metrics)
        verdict = self.judge.judge(scores, criteria)
        return AIEvaluationResult(
            tenantId=tenant,
            runId=run.id,
            caseCode=case.caseCode,
            verdict=verdict.verdict,
            score=verdict.score,
            scores=verdict.scores,
            latencyMs=observation.latencyMs,
            totalTokens=observation.totalTokens,
            cost=observation.cost,
            citationCount=observation.citationCount,
            answerFingerprint=hashlib.sha256(observation.answer.encode()).hexdigest(),
            requestId=observation.requestId,
            notes=verdict.reason,
            createdAt=self._now(),
        )

    def _compareToBaseline(
        self,
        tenant: uuid.UUID,
        run: AIEvaluationRun,
        summary: RunSummary,
        criteria: EvaluationCriteria,
        command: RunSuiteCommand,
    ) -> RegressionReport | None:
        baseline: AIEvaluationRun | None = None
        if command.baselineRunId is not None:
            baseline = self.runStore.getRun(
                tenant, requireUuid(command.baselineRunId, "baselineRunId")
            )
        elif command.compareToPrevious:
            baseline = self.runStore.latestRun(tenant, run.suiteCode, excludeRunId=run.id)
        if baseline is None or baseline.status != "COMPLETED":
            return None
        if baseline.criteriaSignature != run.criteriaSignature:
            return None
        return compareRuns(
            self._summaryOf(tenant, baseline, criteria),
            summary,
            criteria,
            baselineFailures=self._failedCaseCodes(tenant, baseline),
            candidateFailures=self._failedCaseCodes(tenant, run),
        )

    def _summaryOf(
        self, tenant: uuid.UUID, run: AIEvaluationRun, criteria: EvaluationCriteria
    ) -> RunSummary:
        results = self.runStore.listResults(tenant, run.id)
        return self.aggregator.aggregate(results, criteria)

    def _failedCaseCodes(self, tenant: uuid.UUID, run: AIEvaluationRun) -> tuple[str, ...]:
        return tuple(
            sorted(
                item.caseCode
                for item in self.runStore.listResults(tenant, run.id)
                if item.verdict == "FAIL"
            )
        )

    def _requireCase(self, tenant: uuid.UUID, suiteCode: str, caseCode: str) -> AIEvaluationCase:
        self._requireEnabled()
        case = self.caseStore.findCase(
            tenant, ensureCode(suiteCode, "suiteCode"), ensureCode(caseCode, "caseCode")
        )
        if case is None:
            raise AIEvaluationCaseNotFound(f"{suiteCode}:{caseCode}")
        return case

    def _requireRun(self, tenant: uuid.UUID, runId: uuid.UUID | str) -> AIEvaluationRun:
        self._requireEnabled()
        run = self.runStore.getRun(tenant, requireUuid(runId, "runId"))
        if run is None or run.tenantId != tenant:
            raise AIEvaluationRunNotFound(str(runId))
        return run

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI evaluation platform is disabled.")

    def _audit(self, tenant: uuid.UUID, action: str, **kwargs: Any) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(tenant, action, **kwargs)


class EvaluationJobHandler:
    """Phase 13-P handler for the ``EVALUATION`` job kind (§U.13).

    Payload contract::

        {"suiteCode": "RAG_GOLDEN", "method": "BATCH",
         "caseCodes": [...], "compareToPrevious": true}
    """

    JOB_KIND = "EVALUATION"

    def __init__(self, service: EvaluationApplicationService) -> None:
        self.service = service

    def kind(self) -> str:
        return self.JOB_KIND

    def execute(self, job: Any) -> Any:
        from apps.ai.domain.services.jobQueue import JobOutcome

        payload = dict(getattr(job, "payload", {}) or {})
        suite = str(payload.get("suiteCode") or "").strip()
        if not suite:
            raise AIEvaluationInvalid("Evaluation job payload is invalid.")
        rawCodes = payload.get("caseCodes", [])
        if not isinstance(rawCodes, list):
            raise AIEvaluationInvalid("Evaluation job caseCodes must be a list.")
        report = self.service.runSuite(
            job.tenantId,
            RunSuiteCommand(
                suiteCode=suite,
                method=str(payload.get("method", "BATCH") or "BATCH"),
                caseCodes=tuple(str(code) for code in rawCodes),
                compareToPrevious=bool(payload.get("compareToPrevious", True)),
            ),
        )
        return JobOutcome(
            outcome="SUCCEEDED",
            summary={
                "runId": str(report.run.runId),
                "verdict": report.run.verdict,
                "score": report.summary.overallScore,
                "passed": report.summary.passedCount,
                "failed": report.summary.failedCount,
                "regressed": bool(report.regression and report.regression.regressed),
            },
        )


def observationFromRagAnswer(
    answer: Any, *, latencyMs: int = 0, cost: str = "0"
) -> CaseObservation:
    """Adapt a Phase 13-S ``RagAnswer`` into a ``CaseObservation``.

    Keeping the adapter here (rather than importing S into the engine)
    means U can grade the RAG pipeline without the evaluation domain
    knowing that retrieval exists.
    """

    retrieval = getattr(answer, "retrieval", None)
    prompt = getattr(retrieval, "prompt", None)
    return CaseObservation(
        answer=str(getattr(answer, "answer", "") or ""),
        contextText=str(getattr(prompt, "contextText", "") or ""),
        citationCount=len(getattr(answer, "citations", ()) or ()),
        latencyMs=latencyMs,
        totalTokens=int(getattr(prompt, "tokenCount", 0) or 0),
        cost=cost,
        requestId=getattr(answer, "requestId", None),
    )


__all__ = [
    "AUDIT_EVALUATION_COMPLETED",
    "AUDIT_EVALUATION_FAILED",
    "AUDIT_EVALUATION_REGRESSED",
    "AUDIT_EVALUATION_STARTED",
    "CaseDescriptor",
    "EvaluationApplicationService",
    "EvaluationJobHandler",
    "EvaluationSettings",
    "RegisterCaseCommand",
    "ResultDescriptor",
    "RunDescriptor",
    "RunReport",
    "RunSuiteCommand",
    "observationFromRagAnswer",
]
