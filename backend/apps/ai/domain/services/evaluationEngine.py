"""Pure evaluation engine for Phase 13-U.

Everything here is deterministic and offline — that is the point. A
quality gate that needs a live model to decide whether the last change
made things worse is not a gate, it is a second source of flakiness. So
scoring uses closed-form measures over the observation the caller already
has (answer text, evidence, citations, schema, latency, cost).

Contents:

- ``CaseObservation`` — what actually happened when a case ran;
- ``EvaluationEngine`` — computes every metric of ``EVALUATION_METRICS``;
- ``EvaluationJudge`` — turns scores into a case verdict under
  ``EvaluationCriteria``;
- ``RunAggregator`` — turns case verdicts into a run verdict;
- ``compareRuns`` — the regression detector: was this run worse than the
  baseline by more than the tolerance, and on which metric?

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from apps.ai.domain.entities.evaluationRecords import (
    AIEvaluationCase,
    AIEvaluationResult,
)
from apps.ai.domain.exceptions import (
    AIEvaluationCriteriaInvalid,
    AIEvaluationInvalid,
)
from apps.ai.domain.services.aiRules import validateJsonSchema
from apps.ai.domain.valueObjects.evaluationTypes import (
    SCORE_PRECISION,
    EvaluationCriteria,
    MetricScore,
    budgetScore,
    clampScore,
    coverageScore,
    ensureMetric,
    groundednessScore,
    weightedAverage,
    worstVerdict,
)
from apps.ai.domain.valueObjects.retrievalTypes import tokenize


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, ValueError) as error:
        raise AIEvaluationInvalid("Evaluation cost must be a decimal string.") from error


@dataclass(frozen=True)
class CaseObservation:
    """What one case produced when it ran (§U.6)."""

    answer: str
    contextText: str = ""
    citationCount: int = 0
    structuredData: dict[str, Any] | None = None
    latencyMs: int = 0
    totalTokens: int = 0
    cost: str = "0"
    requestId: Any = None
    errorCode: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.answer, str):
            raise AIEvaluationInvalid("Observation answer must be a string.")
        for name in ("citationCount", "latencyMs", "totalTokens"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise AIEvaluationInvalid(f"Observation {name} must be a non-negative integer.")
        object.__setattr__(self, "errorCode", str(self.errorCode or "").strip().upper())

    @property
    def failed(self) -> bool:
        return bool(self.errorCode)


class EvaluationEngine:
    """Computes every metric for one case observation."""

    def __init__(self, *, forbiddenTerms: Sequence[str] = ()) -> None:
        self.forbiddenTerms = tuple(
            str(term).strip().casefold() for term in forbiddenTerms if str(term).strip()
        )

    # ------------------------------------------------------------------
    # Individual metrics (§U.6)
    # ------------------------------------------------------------------
    def groundedness(self, observation: CaseObservation) -> tuple[float, str]:
        if not observation.contextText:
            return (0.0, "No context was supplied; the answer cannot be grounded.")
        score = groundednessScore(observation.answer, observation.contextText)
        return (score, f"{int(score * 100)}% of answer tokens appear in the evidence.")

    def relevance(self, case: AIEvaluationCase, observation: CaseObservation) -> tuple[float, str]:
        """How much of the *answerable* part of the question was addressed.

        Two deliberate refinements over naive token overlap:

        1. tokens of three characters or fewer are ignored — a
           language-neutral stand-in for a stop-word list that drops
           "the", "was", "از", "به" without shipping a dictionary;
        2. when evidence is present, only question tokens that actually
           appear in the evidence are counted. An interrogative like
           "what" or "چرا" can never appear in a good answer, and holding
           the model accountable for echoing it would penalise correct
           answers (this is why the metric is defined against the
           evidence, not against the raw question).
        """

        questionTokens = {token for token in tokenize(case.question) if len(token) > 3}
        if not questionTokens:
            return (1.0, "Question has no content tokens.")
        contextTokens = set(tokenize(observation.contextText))
        answerable = questionTokens & contextTokens if contextTokens else questionTokens
        if not answerable:
            return (0.0, "No question term appears in the evidence.")
        answerTokens = set(tokenize(observation.answer))
        hits = len(answerable & answerTokens)
        score = clampScore(hits / len(answerable))
        return (score, f"{hits}/{len(answerable)} answerable question terms addressed.")

    def completeness(
        self, case: AIEvaluationCase, observation: CaseObservation
    ) -> tuple[float, str]:
        score = coverageScore(case.expectedTerms, observation.answer)
        return (score, f"{len(case.expectedTerms)} expected term(s) checked.")

    def citationCoverage(
        self, case: AIEvaluationCase, observation: CaseObservation
    ) -> tuple[float, str]:
        if case.minimumCitations <= 0:
            return (1.0, "No citation minimum for this case.")
        score = clampScore(observation.citationCount / case.minimumCitations)
        return (
            score,
            f"{observation.citationCount}/{case.minimumCitations} required citations.",
        )

    def schemaValidity(
        self, case: AIEvaluationCase, observation: CaseObservation
    ) -> tuple[float, str]:
        if not case.expectsStructuredOutput:
            return (1.0, "No schema expected.")
        payload = observation.structuredData
        if not isinstance(payload, dict):
            return (0.0, "Structured output was expected but not produced.")
        valid = validateJsonSchema(payload, case.expectedSchema)
        return (1.0 if valid else 0.0, "Schema satisfied." if valid else "Schema violated.")

    def safety(self, case: AIEvaluationCase, observation: CaseObservation) -> tuple[float, str]:
        """Binary: a forbidden term anywhere in the answer fails the case."""

        banned = set(self.forbiddenTerms) | set(case.forbiddenTerms)
        if not banned:
            return (1.0, "No forbidden terms configured.")
        haystack = observation.answer.casefold()
        hits = sorted(term for term in banned if term in haystack)
        if hits:
            return (0.0, f"Forbidden term(s) present: {', '.join(hits[:3])}.")
        return (1.0, "No forbidden term present.")

    def latency(self, case: AIEvaluationCase, observation: CaseObservation) -> tuple[float, str]:
        if case.latencyBudgetMs <= 0:
            return (1.0, "No latency budget for this case.")
        score = budgetScore(observation.latencyMs, case.latencyBudgetMs)
        return (score, f"{observation.latencyMs}ms against {case.latencyBudgetMs}ms budget.")

    def cost(self, case: AIEvaluationCase, observation: CaseObservation) -> tuple[float, str]:
        budget = _decimal(case.costBudget)
        if budget <= 0:
            return (1.0, "No cost budget for this case.")
        observed = _decimal(observation.cost)
        score = budgetScore(float(observed), float(budget))
        return (score, f"{observed} against {budget} budget.")

    # ------------------------------------------------------------------
    # Full sweep
    # ------------------------------------------------------------------
    def scoreCase(
        self,
        case: AIEvaluationCase,
        observation: CaseObservation,
        criteria: EvaluationCriteria,
        *,
        metrics: tuple[str, ...] = (),
    ) -> tuple[MetricScore, ...]:
        if not isinstance(case, AIEvaluationCase):
            raise AIEvaluationInvalid("Scoring requires an AIEvaluationCase.")
        if not isinstance(observation, CaseObservation):
            raise AIEvaluationInvalid("Scoring requires a CaseObservation.")
        if not isinstance(criteria, EvaluationCriteria):
            raise AIEvaluationCriteriaInvalid("Scoring requires EvaluationCriteria.")

        wanted = tuple(ensureMetric(metric) for metric in metrics) or (
            criteria.metrics or ("GROUNDEDNESS", "RELEVANCE", "COMPLETENESS", "SAFETY")
        )
        computed: list[MetricScore] = []
        for metric in wanted:
            if metric == "GROUNDEDNESS":
                score, detail = self.groundedness(observation)
                observed = None
            elif metric == "RELEVANCE":
                score, detail = self.relevance(case, observation)
                observed = None
            elif metric == "COMPLETENESS":
                score, detail = self.completeness(case, observation)
                observed = None
            elif metric == "CITATION_COVERAGE":
                score, detail = self.citationCoverage(case, observation)
                observed = float(observation.citationCount)
            elif metric == "SCHEMA_VALIDITY":
                score, detail = self.schemaValidity(case, observation)
                observed = None
            elif metric == "SAFETY":
                score, detail = self.safety(case, observation)
                observed = None
            elif metric == "LATENCY":
                score, detail = self.latency(case, observation)
                observed = float(observation.latencyMs)
            else:
                score, detail = self.cost(case, observation)
                observed = float(_decimal(observation.cost))
            computed.append(
                MetricScore.evaluate(metric, score, criteria, observed=observed, detail=detail)
            )
        return tuple(computed)


@dataclass(frozen=True)
class CaseVerdict:
    """The judged outcome of one case."""

    verdict: str
    score: float
    scores: tuple[MetricScore, ...]
    failedMetrics: tuple[str, ...] = ()
    missingMetrics: tuple[str, ...] = ()
    reason: str = ""


class EvaluationJudge:
    """Turns metric scores into a case verdict under the criteria (§U.5)."""

    def judge(self, scores: Sequence[MetricScore], criteria: EvaluationCriteria) -> CaseVerdict:
        if not isinstance(criteria, EvaluationCriteria):
            raise AIEvaluationCriteriaInvalid("Judging requires EvaluationCriteria.")
        if not scores:
            return CaseVerdict(
                verdict="FAIL",
                score=0.0,
                scores=(),
                reason="No metric was measured.",
            )
        present = {item.metric for item in scores}
        missing = tuple(metric for metric in criteria.requiredMetrics if metric not in present)
        failed = tuple(item.metric for item in scores if item.verdict == "FAIL")
        verdicts = [item.verdict for item in scores]
        if missing:
            verdicts.append("FAIL")
        overall = weightedAverage({item.metric: item.score for item in scores}, criteria.weights())
        verdict = worstVerdict(verdicts)
        if verdict != "FAIL" and overall < criteria.minimumOverallScore:
            verdict = "WARN"
        reason = (
            f"Required metric(s) not measured: {', '.join(missing)}."
            if missing
            else (
                f"Metric(s) below the failure threshold: {', '.join(failed)}."
                if failed
                else "All measured metrics are within their bands."
            )
        )
        return CaseVerdict(
            verdict=verdict,
            score=overall,
            scores=tuple(scores),
            failedMetrics=failed,
            missingMetrics=missing,
            reason=reason,
        )


@dataclass(frozen=True)
class RunSummary:
    """Aggregate verdict of a whole run (§U.9)."""

    verdict: str
    overallScore: float
    caseCount: int
    passedCount: int
    warnedCount: int
    failedCount: int
    metricAverages: dict[str, float] = field(default_factory=dict)
    reason: str = ""

    @property
    def passRate(self) -> float:
        if not self.caseCount:
            return 0.0
        return round(self.passedCount / self.caseCount, SCORE_PRECISION)

    @property
    def warnRatio(self) -> float:
        if not self.caseCount:
            return 0.0
        return round(self.warnedCount / self.caseCount, SCORE_PRECISION)


class RunAggregator:
    """Turns case verdicts into a run verdict under the criteria."""

    def aggregate(
        self, results: Sequence[AIEvaluationResult], criteria: EvaluationCriteria
    ) -> RunSummary:
        if not isinstance(criteria, EvaluationCriteria):
            raise AIEvaluationCriteriaInvalid("Aggregation requires EvaluationCriteria.")
        if not results:
            return RunSummary(
                verdict="FAIL",
                overallScore=0.0,
                caseCount=0,
                passedCount=0,
                warnedCount=0,
                failedCount=0,
                reason="The suite produced no result.",
            )
        passed = sum(1 for item in results if item.verdict == "PASS")
        warned = sum(1 for item in results if item.verdict == "WARN")
        failed = sum(1 for item in results if item.verdict == "FAIL")
        overall = round(sum(item.score for item in results) / len(results), SCORE_PRECISION)
        averages: dict[str, list[float]] = {}
        for result in results:
            for metric, score in result.metricMap().items():
                averages.setdefault(metric, []).append(score)
        metricAverages = {
            metric: round(sum(values) / len(values), SCORE_PRECISION)
            for metric, values in sorted(averages.items())
        }

        warnRatio = warned / len(results)
        if failed > criteria.maximumFailedCases:
            verdict = "FAIL"
            reason = f"{failed} case(s) failed; at most {criteria.maximumFailedCases} allowed."
        elif overall < criteria.minimumOverallScore:
            verdict = "FAIL"
            reason = f"Overall score {overall} is below the minimum {criteria.minimumOverallScore}."
        elif warnRatio > criteria.maximumWarnRatio:
            verdict = "WARN"
            reason = f"Warn ratio {round(warnRatio, 3)} exceeds {criteria.maximumWarnRatio}."
        elif warned:
            verdict = "WARN"
            reason = f"{warned} case(s) warned."
        else:
            verdict = "PASS"
            reason = "Every case passed within its bands."
        return RunSummary(
            verdict=verdict,
            overallScore=overall,
            caseCount=len(results),
            passedCount=passed,
            warnedCount=warned,
            failedCount=failed,
            metricAverages=metricAverages,
            reason=reason,
        )


@dataclass(frozen=True)
class MetricDelta:
    """How one metric moved between two runs."""

    metric: str
    baseline: float
    candidate: float

    @property
    def delta(self) -> float:
        return round(self.candidate - self.baseline, SCORE_PRECISION)

    @property
    def improved(self) -> bool:
        return self.delta > 0


@dataclass(frozen=True)
class RegressionReport:
    """Did quality get worse, and where (§U.10)."""

    regressed: bool
    overallDelta: float
    tolerance: float
    metricDeltas: tuple[MetricDelta, ...] = ()
    regressedMetrics: tuple[str, ...] = ()
    newFailures: tuple[str, ...] = ()
    fixedFailures: tuple[str, ...] = ()
    reason: str = ""


def compareRuns(
    baseline: RunSummary,
    candidate: RunSummary,
    criteria: EvaluationCriteria,
    *,
    baselineFailures: Sequence[str] = (),
    candidateFailures: Sequence[str] = (),
) -> RegressionReport:
    """Compare two run summaries and flag a regression beyond tolerance.

    A run that merely stays flat is not a regression; a run that drops by
    more than ``criteria.regressionTolerance`` — overall or on any single
    metric — is. New case-level failures always count as a regression, even
    when the averages happen to look fine.
    """

    if not isinstance(criteria, EvaluationCriteria):
        raise AIEvaluationCriteriaInvalid("Comparison requires EvaluationCriteria.")
    tolerance = float(criteria.regressionTolerance)
    overallDelta = round(candidate.overallScore - baseline.overallScore, SCORE_PRECISION)
    metrics = sorted(set(baseline.metricAverages) | set(candidate.metricAverages))
    deltas = tuple(
        MetricDelta(
            metric=metric,
            baseline=baseline.metricAverages.get(metric, 0.0),
            candidate=candidate.metricAverages.get(metric, 0.0),
        )
        for metric in metrics
    )
    regressedMetrics = tuple(item.metric for item in deltas if item.delta < -tolerance)
    baselineSet = {str(code) for code in baselineFailures}
    candidateSet = {str(code) for code in candidateFailures}
    newFailures = tuple(sorted(candidateSet - baselineSet))
    fixedFailures = tuple(sorted(baselineSet - candidateSet))

    regressed = bool(newFailures) or overallDelta < -tolerance or bool(regressedMetrics)
    if newFailures:
        reason = f"New failing case(s): {', '.join(newFailures[:5])}."
    elif overallDelta < -tolerance:
        reason = f"Overall score dropped by {abs(overallDelta)} (tolerance {tolerance})."
    elif regressedMetrics:
        reason = f"Metric(s) regressed: {', '.join(regressedMetrics)}."
    else:
        reason = "No regression beyond tolerance."
    return RegressionReport(
        regressed=regressed,
        overallDelta=overallDelta,
        tolerance=tolerance,
        metricDeltas=deltas,
        regressedMetrics=regressedMetrics,
        newFailures=newFailures,
        fixedFailures=fixedFailures,
        reason=reason,
    )


__all__ = [
    "CaseObservation",
    "CaseVerdict",
    "EvaluationEngine",
    "EvaluationJudge",
    "MetricDelta",
    "RegressionReport",
    "RunAggregator",
    "RunSummary",
    "compareRuns",
]
