"""Pure metric collection, alerting, and health evaluation for 13-W.

Four deterministic services turn recorded facts into operable signals:

- ``MetricCollector`` — merges the samples several contributors produced
  into one coherent set, derives the metrics that are functions of others
  (``aiErrorRatio``, ``aiLatencyAverage``, ``aiLatencyP95``), and refuses
  duplicates that would double-count a counter;
- ``AlertEvaluator`` — compares samples against rules and, crucially,
  *deduplicates*: a breach that is already firing does not open a second
  alert, and a metric that returns to normal resolves the open one.
  Without this an outage produces one alert per collection tick;
- ``HealthEvaluator`` — folds metrics into per-component health and one
  overall verdict, worst component wins;
- ``SnapshotBuilder`` — freezes a window's samples into a storable
  snapshot.

The module performs no I/O and has no Django, HTTP, ORM, queue, network,
or vendor dependency.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import utcNow
from apps.ai.domain.entities.observabilityRecords import (
    AIAlertEvent,
    AIMetricSnapshot,
    ComponentHealth,
    HealthReport,
)
from apps.ai.domain.exceptions import (
    AIAlertRuleInvalid,
    AIMetricInvalid,
    AIObservabilityWindowInvalid,
)
from apps.ai.domain.valueObjects.observabilityTypes import (
    AlertRule,
    MetricSample,
    average,
    coerceValue,
    percentile,
    ratio,
)

#: Components the health evaluator reports on (§W.9).
HEALTH_COMPONENTS = ("PROVIDER", "QUEUE", "RETRIEVAL", "EVALUATION", "FEEDBACK")


@dataclass(frozen=True)
class MetricWindow:
    """The closed-open time range one collection covers."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.start, datetime) or not isinstance(self.end, datetime):
            raise AIObservabilityWindowInvalid("Window bounds must be datetimes.")
        if self.end <= self.start:
            raise AIObservabilityWindowInvalid("The window must end after it starts.")

    @property
    def durationSeconds(self) -> float:
        return round((self.end - self.start).total_seconds(), 3)

    def contains(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


class MetricCollector:
    """Merges contributor samples and derives the computed metrics."""

    def merge(self, groups: Iterable[Sequence[MetricSample]]) -> tuple[MetricSample, ...]:
        """Merge sample groups, refusing a duplicate name+label pair.

        Two contributors publishing the same counter would silently
        double it; the collector treats that as a wiring bug and says so.
        """

        merged: dict[str, MetricSample] = {}
        for group in groups:
            for sample in group:
                if not isinstance(sample, MetricSample):
                    raise AIMetricInvalid("Collection requires MetricSample values.")
                if sample.key in merged:
                    raise AIMetricInvalid(
                        f"Duplicate metric sample for {sample.key}; two contributors "
                        "publish the same series."
                    )
                merged[sample.key] = sample
        return tuple(sorted(merged.values(), key=lambda item: item.key))

    def derive(
        self,
        samples: Sequence[MetricSample],
        *,
        latencies: Sequence[float] = (),
        at: datetime | None = None,
    ) -> tuple[MetricSample, ...]:
        """Add the metrics that are functions of the collected ones."""

        moment = at or utcNow()
        byName = {sample.name: sample.value for sample in samples if not sample.labels}
        derived: list[MetricSample] = []

        total = byName.get("aiRequestsTotal", 0.0)
        failed = byName.get("aiRequestsFailed", 0.0)
        if "aiErrorRatio" not in byName:
            derived.append(MetricSample(name="aiErrorRatio", value=ratio(failed, total), at=moment))
        if latencies:
            if "aiLatencyAverage" not in byName:
                derived.append(
                    MetricSample(name="aiLatencyAverage", value=average(latencies), at=moment)
                )
            if "aiLatencyP95" not in byName:
                derived.append(
                    MetricSample(name="aiLatencyP95", value=percentile(latencies, 0.95), at=moment)
                )
        return tuple(derived)

    def collect(
        self,
        groups: Iterable[Sequence[MetricSample]],
        *,
        latencies: Sequence[float] = (),
        at: datetime | None = None,
    ) -> tuple[MetricSample, ...]:
        merged = self.merge(groups)
        derived = self.derive(merged, latencies=latencies, at=at)
        return tuple(sorted(merged + derived, key=lambda item: item.key))


class SnapshotBuilder:
    """Freezes a window's unlabelled samples into a storable snapshot."""

    def build(
        self,
        tenantId: Any,
        window: MetricWindow,
        samples: Sequence[MetricSample],
        *,
        labels: dict[str, str] | None = None,
        metadata: dict[str, Any] | None = None,
        createdAt: datetime | None = None,
    ) -> AIMetricSnapshot:
        if not isinstance(window, MetricWindow):
            raise AIObservabilityWindowInvalid("Building requires a MetricWindow.")
        metrics: dict[str, float] = {}
        for sample in samples:
            if sample.labels:
                # Labelled series stay in the live exposition; a snapshot is
                # the tenant-level roll-up, not a full time series database.
                continue
            metrics[sample.name] = sample.value
        return AIMetricSnapshot(
            tenantId=tenantId,
            windowStart=window.start,
            windowEnd=window.end,
            metrics=metrics,
            labels=labels or {},
            sampleCount=len(samples),
            metadata=dict(metadata or {}),
            createdAt=createdAt or window.end,
        )


@dataclass(frozen=True)
class AlertDecision:
    """What the evaluator decided about one rule."""

    rule: AlertRule
    observed: float
    breached: bool
    action: str  # OPENED, SUSTAINED, RESOLVED, NONE, SKIPPED
    event: AIAlertEvent | None = None
    reason: str = ""


@dataclass(frozen=True)
class AlertEvaluation:
    """The full verdict of one alerting pass."""

    decisions: tuple[AlertDecision, ...] = ()

    @property
    def opened(self) -> tuple[AIAlertEvent, ...]:
        return tuple(
            item.event for item in self.decisions if item.action == "OPENED" and item.event
        )

    @property
    def resolved(self) -> tuple[AIAlertEvent, ...]:
        return tuple(
            item.event for item in self.decisions if item.action == "RESOLVED" and item.event
        )

    @property
    def sustained(self) -> tuple[AIAlertEvent, ...]:
        return tuple(
            item.event for item in self.decisions if item.action == "SUSTAINED" and item.event
        )


class AlertEvaluator:
    """Compares samples against rules, with de-duplication (§W.8)."""

    def evaluate(
        self,
        rules: Sequence[AlertRule],
        samples: Sequence[MetricSample],
        openEvents: Sequence[AIAlertEvent] = (),
        *,
        tenantId: Any = None,
        snapshotId: Any = None,
        sampleCount: int = 0,
        now: datetime | None = None,
    ) -> AlertEvaluation:
        moment = now or utcNow()
        byName = {sample.name: sample.value for sample in samples if not sample.labels}
        openByRule = {event.ruleCode: event for event in openEvents if event.isActive}
        decisions: list[AlertDecision] = []

        for rule in rules:
            if not isinstance(rule, AlertRule):
                raise AIAlertRuleInvalid("Evaluation requires AlertRule values.")
            existing = openByRule.get(rule.code)
            if rule.metric not in byName:
                decisions.append(
                    AlertDecision(
                        rule=rule,
                        observed=0.0,
                        breached=False,
                        action="SKIPPED",
                        reason="The metric was not collected in this window.",
                    )
                )
                continue
            observed = coerceValue(byName[rule.metric])
            if rule.minimumSamples and sampleCount < rule.minimumSamples:
                decisions.append(
                    AlertDecision(
                        rule=rule,
                        observed=observed,
                        breached=False,
                        action="SKIPPED",
                        reason=(
                            f"Only {sampleCount} sample(s); the rule needs {rule.minimumSamples}."
                        ),
                    )
                )
                continue

            breached = rule.isBreached(observed)
            if breached and existing is None:
                event = AIAlertEvent(
                    tenantId=tenantId,
                    ruleCode=rule.code,
                    metric=rule.metric,
                    severity=rule.severity,
                    state="FIRING",
                    observedValue=observed,
                    threshold=rule.threshold,
                    message=rule.message(observed),
                    firedAt=moment,
                    snapshotId=snapshotId,
                    createdAt=moment,
                )
                decisions.append(
                    AlertDecision(
                        rule=rule,
                        observed=observed,
                        breached=True,
                        action="OPENED",
                        event=event,
                        reason=rule.description or rule.message(observed),
                    )
                )
            elif breached and existing is not None:
                decisions.append(
                    AlertDecision(
                        rule=rule,
                        observed=observed,
                        breached=True,
                        action="SUSTAINED",
                        event=existing,
                        reason="Already firing; not opening a duplicate.",
                    )
                )
            elif not breached and existing is not None:
                existing.resolve(now=moment)
                decisions.append(
                    AlertDecision(
                        rule=rule,
                        observed=observed,
                        breached=False,
                        action="RESOLVED",
                        event=existing,
                        reason="The metric returned inside its threshold.",
                    )
                )
            else:
                decisions.append(
                    AlertDecision(rule=rule, observed=observed, breached=False, action="NONE")
                )
        return AlertEvaluation(decisions=tuple(decisions))


class HealthEvaluator:
    """Folds metrics and alerts into a health verdict (§W.9)."""

    def __init__(
        self,
        *,
        errorRatioDegraded: float = 0.05,
        errorRatioUnhealthy: float = 0.2,
        queueDepthDegraded: float = 50.0,
        queueDepthUnhealthy: float = 200.0,
        feedbackDegraded: float = 0.6,
        evaluationDegraded: float = 0.7,
    ) -> None:
        self.errorRatioDegraded = errorRatioDegraded
        self.errorRatioUnhealthy = errorRatioUnhealthy
        self.queueDepthDegraded = queueDepthDegraded
        self.queueDepthUnhealthy = queueDepthUnhealthy
        self.feedbackDegraded = feedbackDegraded
        self.evaluationDegraded = evaluationDegraded

    def evaluate(
        self,
        tenantId: Any,
        samples: Sequence[MetricSample],
        openEvents: Sequence[AIAlertEvent] = (),
        *,
        now: datetime | None = None,
    ) -> HealthReport:
        byName = {sample.name: sample.value for sample in samples if not sample.labels}
        components = (
            self._provider(byName),
            self._queue(byName),
            self._retrieval(byName),
            self._evaluation(byName),
            self._feedback(byName),
        )
        active = [event for event in openEvents if event.isActive]
        critical = [event for event in active if event.severity == "CRITICAL"]
        statuses = {item.status for item in components}
        if "UNHEALTHY" in statuses or critical:
            overall = "UNHEALTHY"
        elif "DEGRADED" in statuses or active:
            overall = "DEGRADED"
        elif statuses == {"UNKNOWN"}:
            overall = "UNKNOWN"
        else:
            overall = "HEALTHY"
        return HealthReport(
            tenantId=tenantId,
            status=overall,
            components=components,
            activeAlerts=len(active),
            criticalAlerts=len(critical),
            evaluatedAt=now or utcNow(),
        )

    # -- components -----------------------------------------------------
    def _provider(self, byName: dict[str, float]) -> ComponentHealth:
        if "aiRequestsTotal" not in byName or byName.get("aiRequestsTotal", 0.0) <= 0:
            return ComponentHealth(
                component="PROVIDER", status="UNKNOWN", reason="No attempt in this window."
            )
        errorRatio = byName.get("aiErrorRatio", 0.0)
        if errorRatio >= self.errorRatioUnhealthy:
            status, reason = "UNHEALTHY", f"Error ratio {errorRatio}."
        elif errorRatio >= self.errorRatioDegraded:
            status, reason = "DEGRADED", f"Error ratio {errorRatio}."
        else:
            status, reason = "HEALTHY", "Failures are within tolerance."
        return ComponentHealth(
            component="PROVIDER",
            status=status,
            reason=reason,
            metrics={"aiErrorRatio": errorRatio},
        )

    def _queue(self, byName: dict[str, float]) -> ComponentHealth:
        if "aiQueueDepth" not in byName:
            return ComponentHealth(
                component="QUEUE", status="UNKNOWN", reason="Queue depth was not reported."
            )
        depth = byName["aiQueueDepth"]
        if depth >= self.queueDepthUnhealthy:
            status, reason = "UNHEALTHY", f"{int(depth)} job(s) waiting."
        elif depth >= self.queueDepthDegraded:
            status, reason = "DEGRADED", f"{int(depth)} job(s) waiting."
        else:
            status, reason = "HEALTHY", "The queue is keeping up."
        return ComponentHealth(
            component="QUEUE", status=status, reason=reason, metrics={"aiQueueDepth": depth}
        )

    def _retrieval(self, byName: dict[str, float]) -> ComponentHealth:
        if "aiRetrievalDenied" not in byName:
            return ComponentHealth(
                component="RETRIEVAL", status="UNKNOWN", reason="No retrieval in this window."
            )
        denied = byName["aiRetrievalDenied"]
        status = "DEGRADED" if denied > 0 else "HEALTHY"
        reason = (
            f"{int(denied)} retrieval(s) returned no authorized evidence."
            if denied
            else "Every retrieval found authorized evidence."
        )
        return ComponentHealth(
            component="RETRIEVAL",
            status=status,
            reason=reason,
            metrics={"aiRetrievalDenied": denied},
        )

    def _evaluation(self, byName: dict[str, float]) -> ComponentHealth:
        if "aiEvaluationScore" not in byName:
            return ComponentHealth(
                component="EVALUATION", status="UNKNOWN", reason="No evaluation run yet."
            )
        score = byName["aiEvaluationScore"]
        failures = byName.get("aiEvaluationFailures", 0.0)
        if failures > 0:
            status, reason = "UNHEALTHY", f"{int(failures)} case(s) failing."
        elif score < self.evaluationDegraded:
            status, reason = "DEGRADED", f"Latest run scored {score}."
        else:
            status, reason = "HEALTHY", f"Latest run scored {score}."
        return ComponentHealth(
            component="EVALUATION",
            status=status,
            reason=reason,
            metrics={"aiEvaluationScore": score, "aiEvaluationFailures": failures},
        )

    def _feedback(self, byName: dict[str, float]) -> ComponentHealth:
        if "aiFeedbackScore" not in byName:
            return ComponentHealth(
                component="FEEDBACK", status="UNKNOWN", reason="No feedback in this window."
            )
        score = byName["aiFeedbackScore"]
        status = "DEGRADED" if score < self.feedbackDegraded else "HEALTHY"
        return ComponentHealth(
            component="FEEDBACK",
            status=status,
            reason=f"Satisfaction {score}.",
            metrics={"aiFeedbackScore": score},
        )


__all__ = [
    "HEALTH_COMPONENTS",
    "AlertDecision",
    "AlertEvaluation",
    "AlertEvaluator",
    "HealthEvaluator",
    "MetricCollector",
    "MetricWindow",
    "SnapshotBuilder",
]
