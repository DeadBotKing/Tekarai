"""Framework-free observability vocabularies and metric math for 13-W.

Sub-phase W turns everything the platform already records — attempts (N),
audit (O), jobs (P), retrieval (S), evaluation (U), feedback (V) — into
the ten metrics §34 asks for, plus the alerting and health rules that make
those numbers actionable.

Contents:

- ``METRIC_NAMES`` — the closed metric registry, each with a type and a
  unit, so a dashboard never has to guess whether a number is a counter
  or a gauge;
- ``MetricSample`` — one measurement with sanitized labels;
- ``AlertRule`` — a comparison against a threshold with a severity;
- ``renderPrometheus`` — dependency-free exposition text, which is the
  "connect to a monitoring platform" half of §34;
- percentile math used for ``aiLatencyP95``.

The module has no Django, HTTP, ORM, queue, network, or vendor dependency
— and deliberately no Prometheus client library: the exposition format is
a stable text contract, and adding a dependency to print it would violate
the platform's no-new-dependency rule for a few lines of formatting.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.sharedKernel.domain.errors import ValidationFailedError

#: How a metric behaves over time.
METRIC_TYPES = ("COUNTER", "GAUGE", "HISTOGRAM")

#: Units recorded alongside every metric so a chart cannot mislabel an axis.
METRIC_UNITS = ("COUNT", "TOKENS", "CURRENCY", "MILLISECONDS", "RATIO", "SCORE")

#: The closed metric registry. The first ten names are exactly the §34
#: list; the rest are the platform metrics the later sub-phases made
#: measurable (queue depth, retrieval denials, evaluation and memory).
METRIC_REGISTRY: dict[str, tuple[str, str, str]] = {
    "aiRequestsTotal": ("COUNTER", "COUNT", "Metered provider attempts."),
    "aiRequestsFailed": ("COUNTER", "COUNT", "Attempts that ended in failure."),
    "aiTokensTotal": ("COUNTER", "TOKENS", "Input plus output tokens consumed."),
    "aiCostTotal": ("COUNTER", "CURRENCY", "Accrued provider cost."),
    "aiLatencyAverage": ("GAUGE", "MILLISECONDS", "Mean provider latency."),
    "aiLatencyP95": ("GAUGE", "MILLISECONDS", "95th percentile provider latency."),
    "aiProviderFailures": ("COUNTER", "COUNT", "Failures grouped by provider."),
    "aiModelFailures": ("COUNTER", "COUNT", "Failures grouped by model."),
    "aiFallbackCount": ("COUNTER", "COUNT", "Attempts served by a fallback provider."),
    "aiFeedbackScore": ("GAUGE", "SCORE", "Human satisfaction in [0, 1]."),
    "aiQueueDepth": ("GAUGE", "COUNT", "Jobs waiting to be claimed."),
    "aiJobsFailed": ("COUNTER", "COUNT", "Jobs that exhausted their attempts."),
    "aiRetrievalDenied": ("COUNTER", "COUNT", "Retrievals where every candidate was filtered."),
    "aiEvaluationScore": ("GAUGE", "SCORE", "Latest evaluation run score in [0, 1]."),
    "aiEvaluationFailures": ("GAUGE", "COUNT", "Failing cases in the latest run."),
    "aiErrorRatio": ("GAUGE", "RATIO", "Failed attempts divided by total attempts."),
}
METRIC_NAMES = tuple(METRIC_REGISTRY)

#: Health of one component and of the platform as a whole.
HEALTH_STATUSES = ("HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN")

#: Alert severity and lifecycle.
ALERT_SEVERITIES = ("INFO", "WARNING", "CRITICAL")
ALERT_STATES = ("OK", "FIRING", "RESOLVED", "ACKNOWLEDGED")

#: Comparisons an alert rule may make.
ALERT_COMPARISONS = ("ABOVE", "BELOW", "ABOVE_OR_EQUAL", "BELOW_OR_EQUAL")

#: Label keys a sample may carry. Anything else is dropped: labels end up
#: in a monitoring platform outside the tenant boundary, so a free-form
#: label set is a data-leak waiting to happen (§47).
ALLOWED_LABEL_KEYS = (
    "tenant",
    "provider",
    "model",
    "capability",
    "suite",
    "kind",
    "status",
    "reason",
)

MAX_LABEL_VALUE_LENGTH = 64
VALUE_PRECISION = 6

_LABEL_VALUE_PATTERN = re.compile(r"[^A-Za-z0-9_.:@/-]+")


def ensureObservabilityEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            "Unknown observability vocabulary value.", fieldErrors={fieldName: normalized}
        )
    return normalized


def ensureMetricName(value: str) -> str:
    """Metric names are case-sensitive registry keys, not free text."""

    normalized = str(value or "").strip()
    if normalized not in METRIC_REGISTRY:
        raise ValidationFailedError("Unknown metric name.", fieldErrors={"metric": normalized[:40]})
    return normalized


def ensureMetricType(value: str) -> str:
    return ensureObservabilityEnum(value, METRIC_TYPES, "metricType")


def ensureMetricUnit(value: str) -> str:
    return ensureObservabilityEnum(value, METRIC_UNITS, "unit")


def ensureHealthStatus(value: str) -> str:
    return ensureObservabilityEnum(value, HEALTH_STATUSES, "health")


def ensureAlertSeverity(value: str) -> str:
    return ensureObservabilityEnum(value, ALERT_SEVERITIES, "severity")


def ensureAlertState(value: str) -> str:
    return ensureObservabilityEnum(value, ALERT_STATES, "state")


def ensureComparison(value: str) -> str:
    return ensureObservabilityEnum(value, ALERT_COMPARISONS, "comparison")


def metricType(name: str) -> str:
    return METRIC_REGISTRY[ensureMetricName(name)][0]


def metricUnit(name: str) -> str:
    return METRIC_REGISTRY[ensureMetricName(name)][1]


def metricDescription(name: str) -> str:
    return METRIC_REGISTRY[ensureMetricName(name)][2]


def sanitizeLabels(labels: Mapping[str, Any] | None) -> dict[str, str]:
    """Keep only allow-listed keys, with short, character-safe values."""

    if not labels:
        return {}
    if not isinstance(labels, Mapping):
        raise ValidationFailedError("Metric labels must be a mapping.")
    cleaned: dict[str, str] = {}
    for key, value in labels.items():
        normalizedKey = str(key or "").strip()
        if normalizedKey not in ALLOWED_LABEL_KEYS:
            continue
        text = _LABEL_VALUE_PATTERN.sub("_", str(value or "").strip())
        if not text:
            continue
        cleaned[normalizedKey] = text[:MAX_LABEL_VALUE_LENGTH]
    return dict(sorted(cleaned.items()))


def coerceValue(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValidationFailedError("Metric value must be numeric.") from error
    if not math.isfinite(numeric):
        raise ValidationFailedError("Metric value must be finite.")
    return round(numeric, VALUE_PRECISION)


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile — deterministic and dependency-free.

    Nearest-rank (rather than interpolation) is chosen so the reported
    p95 is always a value that actually occurred, which makes it possible
    to go and look at the request behind it.
    """

    if not 0.0 < fraction <= 1.0:
        raise ValidationFailedError("Percentile fraction must lie in (0, 1].")
    ordered = sorted(coerceValue(value) for value in values)
    if not ordered:
        return 0.0
    rank = max(1, math.ceil(fraction * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def average(values: Sequence[float]) -> float:
    materialized = [coerceValue(value) for value in values]
    if not materialized:
        return 0.0
    return round(sum(materialized) / len(materialized), VALUE_PRECISION)


def ratio(numerator: float, denominator: float) -> float:
    """Safe ratio in ``[0, 1]``; a zero denominator means "no signal"."""

    if denominator <= 0:
        return 0.0
    return round(min(1.0, max(0.0, numerator / denominator)), VALUE_PRECISION)


@dataclass(frozen=True)
class MetricSample:
    """One measurement of one registered metric."""

    name: str
    value: float
    labels: dict[str, str] = field(default_factory=dict)
    at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", ensureMetricName(self.name))
        object.__setattr__(self, "value", coerceValue(self.value))
        object.__setattr__(self, "labels", sanitizeLabels(self.labels))

    @property
    def type(self) -> str:
        return metricType(self.name)

    @property
    def unit(self) -> str:
        return metricUnit(self.name)

    @property
    def key(self) -> str:
        rendered = ",".join(f"{key}={value}" for key, value in self.labels.items())
        return f"{self.name}{{{rendered}}}" if rendered else self.name


@dataclass(frozen=True)
class AlertRule:
    """A comparison against a threshold, with a severity (§W.7)."""

    code: str
    metric: str
    comparison: str = "ABOVE"
    threshold: float = 0.0
    severity: str = "WARNING"
    description: str = ""
    minimumSamples: int = 0

    def __post_init__(self) -> None:
        code = str(self.code or "").strip().upper().replace(" ", "_")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", code):
            raise ValidationFailedError(
                "Alert rule code must be an uppercase identifier.",
                fieldErrors={"code": code[:40]},
            )
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "metric", ensureMetricName(self.metric))
        object.__setattr__(self, "comparison", ensureComparison(self.comparison))
        object.__setattr__(self, "severity", ensureAlertSeverity(self.severity))
        object.__setattr__(self, "threshold", coerceValue(self.threshold))
        if not isinstance(self.minimumSamples, int) or isinstance(self.minimumSamples, bool):
            raise ValidationFailedError("minimumSamples must be an integer.")
        if self.minimumSamples < 0:
            raise ValidationFailedError("minimumSamples cannot be negative.")

    def isBreached(self, value: float) -> bool:
        observed = coerceValue(value)
        if self.comparison == "ABOVE":
            return observed > self.threshold
        if self.comparison == "ABOVE_OR_EQUAL":
            return observed >= self.threshold
        if self.comparison == "BELOW":
            return observed < self.threshold
        return observed <= self.threshold

    def message(self, value: float) -> str:
        return (
            f"{self.metric} is {coerceValue(value)}; rule {self.code} expects it not "
            f"{self.comparison.replace('_', ' ').lower()} {self.threshold}."
        )

    def signature(self) -> str:
        return f"{self.code}|{self.metric}|{self.comparison}|{self.threshold}|{self.severity}"


def defaultAlertRules() -> tuple[AlertRule, ...]:
    """The shipped rule set: the four failures that actually hurt (§W.7)."""

    return (
        AlertRule(
            code="AI_ERROR_RATIO_HIGH",
            metric="aiErrorRatio",
            comparison="ABOVE",
            threshold=0.1,
            severity="CRITICAL",
            description="More than one in ten provider attempts is failing.",
            minimumSamples=10,
        ),
        AlertRule(
            code="AI_LATENCY_P95_HIGH",
            metric="aiLatencyP95",
            comparison="ABOVE",
            threshold=15_000.0,
            severity="WARNING",
            description="95th percentile latency exceeds fifteen seconds.",
        ),
        AlertRule(
            code="AI_QUEUE_BACKLOG",
            metric="aiQueueDepth",
            comparison="ABOVE",
            threshold=100.0,
            severity="WARNING",
            description="The async queue is falling behind.",
        ),
        AlertRule(
            code="AI_FEEDBACK_LOW",
            metric="aiFeedbackScore",
            comparison="BELOW",
            threshold=0.5,
            severity="WARNING",
            description="Human satisfaction dropped below half.",
        ),
        AlertRule(
            code="AI_EVALUATION_LOW",
            metric="aiEvaluationScore",
            comparison="BELOW",
            threshold=0.6,
            severity="CRITICAL",
            description="The latest evaluation run scored below the acceptance bar.",
        ),
    )


def renderPrometheus(samples: Iterable[MetricSample]) -> str:
    """Render samples as Prometheus text exposition (§34).

    Written by hand on purpose: the format is a stable, tiny text
    contract, and pulling in a client library to produce it would add a
    dependency the platform does not otherwise need.
    """

    grouped: dict[str, list[MetricSample]] = {}
    for sample in samples:
        if not isinstance(sample, MetricSample):
            raise ValidationFailedError("Rendering requires MetricSample values.")
        grouped.setdefault(sample.name, []).append(sample)

    lines: list[str] = []
    for name in sorted(grouped):
        lines.append(f"# HELP {name} {metricDescription(name)}")
        lines.append(f"# TYPE {name} {metricType(name).lower()}")
        for sample in sorted(grouped[name], key=lambda item: item.key):
            if sample.labels:
                rendered = ",".join(f'{key}="{value}"' for key, value in sample.labels.items())
                lines.append(f"{name}{{{rendered}}} {sample.value}")
            else:
                lines.append(f"{name} {sample.value}")
    return "\n".join(lines) + ("\n" if lines else "")


__all__ = [
    "ALERT_COMPARISONS",
    "ALERT_SEVERITIES",
    "ALERT_STATES",
    "ALLOWED_LABEL_KEYS",
    "HEALTH_STATUSES",
    "MAX_LABEL_VALUE_LENGTH",
    "METRIC_NAMES",
    "METRIC_REGISTRY",
    "METRIC_TYPES",
    "METRIC_UNITS",
    "VALUE_PRECISION",
    "AlertRule",
    "MetricSample",
    "average",
    "coerceValue",
    "defaultAlertRules",
    "ensureAlertSeverity",
    "ensureAlertState",
    "ensureComparison",
    "ensureHealthStatus",
    "ensureMetricName",
    "ensureMetricType",
    "ensureMetricUnit",
    "ensureObservabilityEnum",
    "metricDescription",
    "metricType",
    "metricUnit",
    "percentile",
    "ratio",
    "renderPrometheus",
    "sanitizeLabels",
]
