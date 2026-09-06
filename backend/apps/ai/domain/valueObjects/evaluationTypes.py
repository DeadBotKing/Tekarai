"""Framework-free evaluation vocabularies, metrics, and criteria (13-U).

This module answers Open Question #9 from sub-phase A — *how is AI output
evaluated and what counts as acceptable* — with two explicit objects:

- ``EVALUATION_METRICS`` — the closed set of things the platform measures;
- ``EvaluationCriteria`` — the per-metric thresholds, weights, and required
  metrics that turn raw scores into a ``PASS`` / ``WARN`` / ``FAIL``
  verdict. Acceptance is therefore configuration, not folklore.

It also carries the deterministic scoring math (coverage, groundedness,
budget ratios) so a verdict never depends on a model being reachable: an
offline evaluation run produces the same numbers on every machine.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency.
Evaluation *methods* keep using the Phase 13-B ``EVALUATION_METHODS``
vocabulary; U adds no parallel list.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from apps.ai.domain.valueObjects.aiTypes import EVALUATION_METHODS, ensureEnum
from apps.ai.domain.valueObjects.retrievalTypes import tokenize
from apps.sharedKernel.domain.errors import ValidationFailedError

#: What the platform measures about one AI answer (§32).
EVALUATION_METRICS = (
    "GROUNDEDNESS",
    "RELEVANCE",
    "COMPLETENESS",
    "CITATION_COVERAGE",
    "SCHEMA_VALIDITY",
    "SAFETY",
    "LATENCY",
    "COST",
)

#: Verdict of one case or one run.
EVALUATION_VERDICTS = ("PASS", "WARN", "FAIL")

#: Lifecycle of an evaluation run.
RUN_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
TERMINAL_RUN_STATUSES = ("COMPLETED", "FAILED", "CANCELLED")

#: Metrics where a *lower* raw observation is better; the scorer inverts
#: them against their budget so every stored score means "higher is better".
INVERTED_METRICS = ("LATENCY", "COST")

#: Absolute guards independent of configuration (§U.12).
MAX_CASES_PER_SUITE = 1000
MAX_SUITE_CODE_LENGTH = 80
SCORE_PRECISION = 6


def ensureEvaluationEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown evaluation vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureMetric(value: str) -> str:
    return ensureEvaluationEnum(value, EVALUATION_METRICS, "metric")


def ensureVerdict(value: str) -> str:
    return ensureEvaluationEnum(value, EVALUATION_VERDICTS, "verdict")


def ensureRunStatus(value: str) -> str:
    return ensureEvaluationEnum(value, RUN_STATUSES, "status")


def ensureEvaluationMethod(value: str) -> str:
    return ensureEnum(value, EVALUATION_METHODS, "evaluationMethod")


def clampScore(value: float) -> float:
    """Coerce any raw number into the closed unit interval."""

    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValidationFailedError("Evaluation score must be numeric.") from error
    if not math.isfinite(numeric):
        raise ValidationFailedError("Evaluation score must be finite.")
    return round(min(1.0, max(0.0, numeric)), SCORE_PRECISION)


def coverageScore(expected: Iterable[str], produced: str) -> float:
    """Fraction of expected terms present in the produced text.

    Term-level and tokenizer-free, so it behaves identically for Persian
    and Latin text and never needs a model call.
    """

    terms = [str(item).strip() for item in expected if str(item).strip()]
    if not terms:
        return 1.0
    haystack = set(tokenize(produced))
    if not haystack:
        return 0.0
    hits = 0
    for term in terms:
        termTokens = set(tokenize(term))
        if termTokens and termTokens.issubset(haystack):
            hits += 1
    return clampScore(hits / len(terms))


def groundednessScore(answer: str, context: str) -> float:
    """Fraction of the answer's content tokens that the context supports.

    A cheap, deterministic proxy for "did the model invent this?": tokens
    that never appear in the evidence are unsupported. Perfect it is not —
    it is a *floor* that catches free-form invention, and the contract says
    so out loud (decision U-D3).
    """

    answerTokens = [token for token in tokenize(answer) if len(token) > 2]
    if not answerTokens:
        return 0.0
    contextTokens = set(tokenize(context))
    if not contextTokens:
        return 0.0
    supported = sum(1 for token in answerTokens if token in contextTokens)
    return clampScore(supported / len(answerTokens))


def budgetScore(observed: float, budget: float) -> float:
    """Score an inverted metric against its budget (1.0 at or under it)."""

    if budget <= 0:
        return 1.0
    if observed <= 0:
        return 1.0
    return clampScore(min(1.0, budget / float(observed)))


def weightedAverage(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Weighted mean of metric scores; missing weights default to 1.0."""

    total = 0.0
    weightSum = 0.0
    for metric, score in scores.items():
        weight = float(weights.get(metric, 1.0))
        if weight < 0:
            raise ValidationFailedError("Metric weights cannot be negative.")
        total += clampScore(score) * weight
        weightSum += weight
    if weightSum <= 0:
        return 0.0
    return round(total / weightSum, SCORE_PRECISION)


@dataclass(frozen=True)
class MetricThreshold:
    """Acceptance band of one metric (§U.5)."""

    metric: str
    failBelow: float = 0.5
    warnBelow: float = 0.8
    weight: float = 1.0
    required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", ensureMetric(self.metric))
        for name in ("failBelow", "warnBelow"):
            value = float(getattr(self, name))
            if not 0.0 <= value <= 1.0:
                raise ValidationFailedError(
                    "Metric thresholds must lie in [0, 1].", fieldErrors={name: str(value)}
                )
            object.__setattr__(self, name, round(value, SCORE_PRECISION))
        if self.failBelow > self.warnBelow:
            raise ValidationFailedError("failBelow cannot exceed warnBelow.")
        if float(self.weight) < 0:
            raise ValidationFailedError("Metric weight cannot be negative.")
        object.__setattr__(self, "weight", float(self.weight))
        if not isinstance(self.required, bool):
            raise ValidationFailedError("Metric required flag must be boolean.")

    def verdictFor(self, score: float) -> str:
        value = clampScore(score)
        if value < self.failBelow:
            return "FAIL"
        if value < self.warnBelow:
            return "WARN"
        return "PASS"


@dataclass(frozen=True)
class EvaluationCriteria:
    """What "acceptable" means — the answer to Open Question #9."""

    thresholds: tuple[MetricThreshold, ...] = ()
    minimumOverallScore: float = 0.7
    maximumFailedCases: int = 0
    maximumWarnRatio: float = 0.3
    regressionTolerance: float = 0.02

    def __post_init__(self) -> None:
        seen: list[str] = []
        for threshold in self.thresholds:
            if not isinstance(threshold, MetricThreshold):
                raise ValidationFailedError("Criteria require MetricThreshold values.")
            if threshold.metric in seen:
                raise ValidationFailedError(
                    "Duplicate metric threshold.", fieldErrors={"metric": threshold.metric}
                )
            seen.append(threshold.metric)
        if not 0.0 <= float(self.minimumOverallScore) <= 1.0:
            raise ValidationFailedError("minimumOverallScore must lie in [0, 1].")
        if self.maximumFailedCases < 0:
            raise ValidationFailedError("maximumFailedCases cannot be negative.")
        if not 0.0 <= float(self.maximumWarnRatio) <= 1.0:
            raise ValidationFailedError("maximumWarnRatio must lie in [0, 1].")
        if not 0.0 <= float(self.regressionTolerance) <= 1.0:
            raise ValidationFailedError("regressionTolerance must lie in [0, 1].")

    def thresholdFor(self, metric: str) -> MetricThreshold:
        wanted = ensureMetric(metric)
        for threshold in self.thresholds:
            if threshold.metric == wanted:
                return threshold
        return MetricThreshold(metric=wanted)

    @property
    def metrics(self) -> tuple[str, ...]:
        return tuple(threshold.metric for threshold in self.thresholds)

    @property
    def requiredMetrics(self) -> tuple[str, ...]:
        return tuple(item.metric for item in self.thresholds if item.required)

    def weights(self) -> dict[str, float]:
        return {item.metric: item.weight for item in self.thresholds}

    def signature(self) -> str:
        """Compact identity recorded on a run, so two runs are comparable."""

        parts = [
            f"{item.metric}:{item.failBelow}/{item.warnBelow}@{item.weight}"
            f"{'!' if item.required else ''}"
            for item in sorted(self.thresholds, key=lambda item: item.metric)
        ]
        return (
            "|".join(parts)
            + f"#min={self.minimumOverallScore}"
            + f",fail={self.maximumFailedCases}"
            + f",warn={self.maximumWarnRatio}"
        )

    @classmethod
    def platformDefault(cls) -> EvaluationCriteria:
        """Shipped acceptance bar; groundedness and safety are mandatory."""

        return cls(
            thresholds=(
                MetricThreshold(
                    metric="GROUNDEDNESS", failBelow=0.5, warnBelow=0.75, weight=2.0, required=True
                ),
                MetricThreshold(metric="RELEVANCE", failBelow=0.4, warnBelow=0.7, weight=1.5),
                MetricThreshold(metric="COMPLETENESS", failBelow=0.4, warnBelow=0.7),
                MetricThreshold(metric="CITATION_COVERAGE", failBelow=0.5, warnBelow=0.8),
                MetricThreshold(
                    metric="SAFETY", failBelow=1.0, warnBelow=1.0, weight=2.0, required=True
                ),
                MetricThreshold(metric="SCHEMA_VALIDITY", failBelow=1.0, warnBelow=1.0),
                MetricThreshold(metric="LATENCY", failBelow=0.25, warnBelow=0.5, weight=0.5),
                MetricThreshold(metric="COST", failBelow=0.25, warnBelow=0.5, weight=0.5),
            ),
            minimumOverallScore=0.7,
            maximumFailedCases=0,
            maximumWarnRatio=0.3,
            regressionTolerance=0.02,
        )


def worstVerdict(verdicts: Sequence[str]) -> str:
    """Combine verdicts: any FAIL wins, then WARN, else PASS."""

    normalized = [ensureVerdict(value) for value in verdicts]
    if "FAIL" in normalized:
        return "FAIL"
    if "WARN" in normalized:
        return "WARN"
    return "PASS"


@dataclass(frozen=True)
class MetricScore:
    """One measured metric with its verdict."""

    metric: str
    score: float
    verdict: str = "PASS"
    observed: float | None = None
    detail: str = ""
    weight: float = 1.0
    required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", ensureMetric(self.metric))
        object.__setattr__(self, "score", clampScore(self.score))
        object.__setattr__(self, "verdict", ensureVerdict(self.verdict))
        if float(self.weight) < 0:
            raise ValidationFailedError("Metric weight cannot be negative.")

    @classmethod
    def evaluate(
        cls,
        metric: str,
        score: float,
        criteria: EvaluationCriteria,
        *,
        observed: float | None = None,
        detail: str = "",
    ) -> MetricScore:
        threshold = criteria.thresholdFor(metric)
        value = clampScore(score)
        return cls(
            metric=threshold.metric,
            score=value,
            verdict=threshold.verdictFor(value),
            observed=observed,
            detail=detail,
            weight=threshold.weight,
            required=threshold.required,
        )


__all__ = [
    "EVALUATION_METRICS",
    "EVALUATION_VERDICTS",
    "INVERTED_METRICS",
    "MAX_CASES_PER_SUITE",
    "MAX_SUITE_CODE_LENGTH",
    "RUN_STATUSES",
    "SCORE_PRECISION",
    "TERMINAL_RUN_STATUSES",
    "EvaluationCriteria",
    "MetricScore",
    "MetricThreshold",
    "budgetScore",
    "clampScore",
    "coverageScore",
    "ensureEvaluationEnum",
    "ensureEvaluationMethod",
    "ensureMetric",
    "ensureRunStatus",
    "ensureVerdict",
    "groundednessScore",
    "weightedAverage",
    "worstVerdict",
]
