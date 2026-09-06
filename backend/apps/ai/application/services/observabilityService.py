"""Application orchestration for the Phase 13-W observability platform.

``ObservabilityApplicationService`` turns what the platform already
records into the ten metrics §34 asks for, the alerts that make them
actionable, and the Prometheus exposition that connects them to a
monitoring platform.

Behaviour worth stating once:

- **W owns no measurement of its own.** Every number comes from a
  ``MetricContributor``: usage from Phase 13-N, jobs from P, evaluation
  from U, feedback from V. Adding a source is registering one more
  contributor, not editing the collector.
- **A broken contributor degrades the snapshot, it does not lose it.**
  Monitoring that goes dark exactly when one subsystem breaks is
  monitoring that cannot be trusted, so a contributor that raises is
  recorded as a failed source and the rest of the window still ships.
- **Alerts are deduplicated.** A sustained breach keeps one open alert
  instead of one per collection tick, and recovery resolves it.
- **Labels are allow-listed.** Metrics leave the tenant boundary, so no
  free-form label may ride along (§47).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.entities.observabilityRecords import (
    AIAlertEvent,
    AIMetricSnapshot,
    HealthReport,
)
from apps.ai.domain.exceptions import (
    AIAlertNotFound,
    AIAlertRuleInvalid,
    AIConfigurationError,
    AIMetricInvalid,
    AIObservabilityWindowInvalid,
)
from apps.ai.domain.observabilityPorts import (
    AlertEventStore,
    MetricContributor,
    MetricSnapshotStore,
    ObservabilityAuditLogger,
)
from apps.ai.domain.services.observabilityEngine import (
    AlertEvaluation,
    AlertEvaluator,
    HealthEvaluator,
    MetricCollector,
    MetricWindow,
    SnapshotBuilder,
)
from apps.ai.domain.valueObjects.observabilityTypes import (
    AlertRule,
    MetricSample,
    defaultAlertRules,
    ensureAlertSeverity,
    ensureAlertState,
    ratio,
    renderPrometheus,
)

#: Audit actions appended by W (registered in the Phase 13-O vocabulary).
AUDIT_ALERT_FIRED = "ALERT_FIRED"
AUDIT_ALERT_RESOLVED = "ALERT_RESOLVED"
AUDIT_ALERT_ACKNOWLEDGED = "ALERT_ACKNOWLEDGED"


@dataclass(frozen=True)
class ObservabilitySettings:
    """Configuration-driven defaults (Master Specification §42)."""

    enabled: bool = True
    collectionWindowMinutes: int = 60
    maxWindowHours: int = 24
    alertingEnabled: bool = True
    errorRatioThreshold: float = 0.1
    latencyP95ThresholdMs: int = 15_000
    queueDepthThreshold: int = 100
    feedbackScoreThreshold: float = 0.5
    evaluationScoreThreshold: float = 0.6
    snapshotRetentionDays: int = 90
    alertRetentionDays: int = 365

    def __post_init__(self) -> None:
        if self.collectionWindowMinutes < 1:
            raise AIConfigurationError("aiObservabilityWindowMinutes must be positive.")
        if self.maxWindowHours < 1:
            raise AIConfigurationError("aiObservabilityMaxWindowHours must be positive.")
        for name in ("snapshotRetentionDays", "alertRetentionDays"):
            if getattr(self, name) < 1:
                raise AIConfigurationError(f"{name} must be positive.")
        # Building the rules here means an impossible configuration fails at
        # construction, not on the first collection.
        self.alertRules()

    def alertRules(self) -> tuple[AlertRule, ...]:
        """Shipped rules with their thresholds taken from configuration."""

        overrides = {
            "AI_ERROR_RATIO_HIGH": float(self.errorRatioThreshold),
            "AI_LATENCY_P95_HIGH": float(self.latencyP95ThresholdMs),
            "AI_QUEUE_BACKLOG": float(self.queueDepthThreshold),
            "AI_FEEDBACK_LOW": float(self.feedbackScoreThreshold),
            "AI_EVALUATION_LOW": float(self.evaluationScoreThreshold),
        }
        return tuple(
            AlertRule(
                code=rule.code,
                metric=rule.metric,
                comparison=rule.comparison,
                threshold=overrides.get(rule.code, rule.threshold),
                severity=rule.severity,
                description=rule.description,
                minimumSamples=rule.minimumSamples,
            )
            for rule in defaultAlertRules()
        )

    @classmethod
    def fromDjangoSettings(cls) -> ObservabilitySettings:
        return cls(
            enabled=bool(getattr(djangoSettings, "AI_OBSERVABILITY_ENABLED", True)),
            collectionWindowMinutes=int(
                getattr(djangoSettings, "AI_OBSERVABILITY_WINDOW_MINUTES", 60) or 60
            ),
            maxWindowHours=int(
                getattr(djangoSettings, "AI_OBSERVABILITY_MAX_WINDOW_HOURS", 24) or 24
            ),
            alertingEnabled=bool(getattr(djangoSettings, "AI_ALERTING_ENABLED", True)),
            errorRatioThreshold=float(getattr(djangoSettings, "AI_ALERT_ERROR_RATIO", 0.1) or 0.1),
            latencyP95ThresholdMs=int(
                getattr(djangoSettings, "AI_ALERT_LATENCY_P95_MS", 15_000) or 15_000
            ),
            queueDepthThreshold=int(getattr(djangoSettings, "AI_ALERT_QUEUE_DEPTH", 100) or 100),
            feedbackScoreThreshold=float(
                getattr(djangoSettings, "AI_ALERT_FEEDBACK_SCORE", 0.5) or 0.5
            ),
            evaluationScoreThreshold=float(
                getattr(djangoSettings, "AI_ALERT_EVALUATION_SCORE", 0.6) or 0.6
            ),
            snapshotRetentionDays=int(
                getattr(djangoSettings, "AI_OBSERVABILITY_SNAPSHOT_RETENTION_DAYS", 90) or 90
            ),
            alertRetentionDays=int(
                getattr(djangoSettings, "AI_OBSERVABILITY_ALERT_RETENTION_DAYS", 365) or 365
            ),
        )


@dataclass(frozen=True)
class CollectionResult:
    """Everything one collection pass produced (§W.6)."""

    snapshot: AIMetricSnapshot
    samples: tuple[MetricSample, ...]
    evaluation: AlertEvaluation | None = None
    failedSources: tuple[tuple[str, str], ...] = ()

    @property
    def openedAlerts(self) -> tuple[AIAlertEvent, ...]:
        return () if self.evaluation is None else self.evaluation.opened

    @property
    def resolvedAlerts(self) -> tuple[AIAlertEvent, ...]:
        return () if self.evaluation is None else self.evaluation.resolved

    @property
    def isDegraded(self) -> bool:
        return bool(self.failedSources)


@dataclass(frozen=True)
class AlertDescriptor:
    """Safe read model of one alert event."""

    alertId: uuid.UUID
    tenantId: uuid.UUID
    ruleCode: str
    metric: str
    severity: str
    state: str
    observedValue: float
    threshold: float
    message: str
    firedAt: datetime
    resolvedAt: datetime | None
    acknowledgedAt: datetime | None
    acknowledgedBy: uuid.UUID | None

    @classmethod
    def of(cls, alert: AIAlertEvent) -> AlertDescriptor:
        return cls(
            alertId=alert.id,
            tenantId=alert.tenantId,
            ruleCode=alert.ruleCode,
            metric=alert.metric,
            severity=alert.severity,
            state=alert.state,
            observedValue=alert.observedValue,
            threshold=alert.threshold,
            message=alert.message,
            firedAt=alert.firedAt,
            resolvedAt=alert.resolvedAt,
            acknowledgedAt=alert.acknowledgedAt,
            acknowledgedBy=alert.acknowledgedBy,
        )


class ObservabilityApplicationService:
    """Tenant-scoped facade for metrics, alerts, health, and exposition."""

    def __init__(
        self,
        snapshotStore: MetricSnapshotStore,
        alertStore: AlertEventStore,
        *,
        contributors: Sequence[MetricContributor] = (),
        settings: ObservabilitySettings | None = None,
        auditLogger: ObservabilityAuditLogger | None = None,
        collector: MetricCollector | None = None,
        builder: SnapshotBuilder | None = None,
        evaluator: AlertEvaluator | None = None,
        health: HealthEvaluator | None = None,
        now: Any = utcNow,
    ) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self.snapshotStore = snapshotStore
        self.alertStore = alertStore
        self.contributors = list(contributors)
        self.settings = settings or ObservabilitySettings()
        self.auditLogger = auditLogger
        self.collector = collector or MetricCollector()
        self.builder = builder or SnapshotBuilder()
        self.evaluator = evaluator or AlertEvaluator()
        self.health = health or HealthEvaluator()
        self._now = now

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def registerContributor(self, contributor: MetricContributor) -> MetricContributor:
        if not hasattr(contributor, "collect") or not hasattr(contributor, "name"):
            raise AIMetricInvalid("A contributor must expose name() and collect().")
        self.contributors.append(contributor)
        return contributor

    # ------------------------------------------------------------------
    # Collection (§W.6)
    # ------------------------------------------------------------------
    def collect(
        self,
        tenantId: uuid.UUID | str,
        *,
        window: MetricWindow | None = None,
        evaluateAlerts: bool | None = None,
        labels: dict[str, str] | None = None,
    ) -> CollectionResult:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        chosen = window or self.defaultWindow()
        if not isinstance(chosen, MetricWindow):
            raise AIObservabilityWindowInvalid("Collection requires a MetricWindow.")
        maxSeconds = self.settings.maxWindowHours * 3600
        if chosen.durationSeconds > maxSeconds:
            raise AIObservabilityWindowInvalid(
                "The collection window exceeds the configured maximum."
            )

        groups: list[Sequence[MetricSample]] = []
        latencies: list[float] = []
        failures: list[tuple[str, str]] = []
        for contributor in self.contributors:
            name = str(contributor.name())
            try:
                produced = contributor.collect(tenant, chosen)
            except Exception as error:  # noqa: BLE001 - one blind source, not a blind window
                failures.append((name, str(getattr(error, "code", type(error).__name__))))
                continue
            if produced is None:
                continue
            samples = tuple(produced)
            for sample in samples:
                if not isinstance(sample, MetricSample):
                    raise AIMetricInvalid(
                        f"Contributor {name} produced something other than a MetricSample."
                    )
            groups.append(samples)
            latencies.extend(getattr(contributor, "latencies", ()) or ())

        samples = self.collector.collect(groups, latencies=latencies, at=chosen.end)
        snapshot = self.builder.build(
            tenant,
            chosen,
            samples,
            labels=labels,
            metadata={
                "contributors": [str(item.name()) for item in self.contributors],
                "failedSources": [name for name, _ in failures],
            },
            createdAt=self._now(),
        )
        stored = self.snapshotStore.saveSnapshot(snapshot)

        evaluation: AlertEvaluation | None = None
        shouldEvaluate = self.settings.alertingEnabled if evaluateAlerts is None else evaluateAlerts
        if shouldEvaluate:
            evaluation = self._runAlerting(tenant, samples, stored)
        return CollectionResult(
            snapshot=stored,
            samples=samples,
            evaluation=evaluation,
            failedSources=tuple(failures),
        )

    def defaultWindow(self, *, now: datetime | None = None) -> MetricWindow:
        end = now or self._now()
        return MetricWindow(
            start=end - timedelta(minutes=self.settings.collectionWindowMinutes), end=end
        )

    # ------------------------------------------------------------------
    # Exposition (§34)
    # ------------------------------------------------------------------
    def exportPrometheus(
        self, tenantId: uuid.UUID | str, *, samples: Sequence[MetricSample] | None = None
    ) -> str:
        """Render the latest snapshot (or given samples) as exposition text."""

        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if samples is not None:
            return renderPrometheus(samples)
        snapshot = self.snapshotStore.latestSnapshot(tenant)
        if snapshot is None:
            return ""
        return renderPrometheus(snapshot.toSamples())

    # ------------------------------------------------------------------
    # Alerts (§W.8)
    # ------------------------------------------------------------------
    def alertRules(self) -> tuple[AlertRule, ...]:
        return self.settings.alertRules()

    def evaluateAlerts(
        self,
        tenantId: uuid.UUID | str,
        samples: Sequence[MetricSample],
        *,
        snapshotId: uuid.UUID | None = None,
        rules: Sequence[AlertRule] | None = None,
    ) -> AlertEvaluation:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        chosen = tuple(rules) if rules is not None else self.alertRules()
        for rule in chosen:
            if not isinstance(rule, AlertRule):
                raise AIAlertRuleInvalid("Alert evaluation requires AlertRule values.")
        return self._runAlerting(tenant, samples, None, rules=chosen, snapshotId=snapshotId)

    def listAlerts(
        self,
        tenantId: uuid.UUID | str,
        *,
        states: tuple[str, ...] = (),
        severities: tuple[str, ...] = (),
        ruleCode: str = "",
        limit: int = 200,
    ) -> tuple[AlertDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        alerts = self.alertStore.listAlerts(
            tenant,
            states=tuple(ensureAlertState(value) for value in states),
            severities=tuple(ensureAlertSeverity(value) for value in severities),
            ruleCode=str(ruleCode or "").strip().upper(),
            limit=limit,
        )
        return tuple(AlertDescriptor.of(alert) for alert in alerts)

    def acknowledgeAlert(
        self,
        tenantId: uuid.UUID | str,
        alertId: uuid.UUID | str,
        *,
        actorId: uuid.UUID | str | None = None,
    ) -> AlertDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        alert = self._requireAlert(tenant, alertId)
        alert.acknowledge(actorId=actorId, now=self._now())
        stored = self.alertStore.updateAlert(alert)
        self._audit(
            tenant,
            AUDIT_ALERT_ACKNOWLEDGED,
            outcome="UPDATED",
            actorId=stored.acknowledgedBy,
            contextSources=(stored.ruleCode,),
            detail={"alertId": str(stored.id), "metric": stored.metric},
        )
        return AlertDescriptor.of(stored)

    def describeAlert(self, tenantId: uuid.UUID | str, alertId: uuid.UUID | str) -> AlertDescriptor:
        return AlertDescriptor.of(self._requireAlert(requireUuid(tenantId, "tenantId"), alertId))

    # ------------------------------------------------------------------
    # Health (§W.9)
    # ------------------------------------------------------------------
    def healthReport(
        self, tenantId: uuid.UUID | str, *, samples: Sequence[MetricSample] | None = None
    ) -> HealthReport:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        if samples is None:
            snapshot = self.snapshotStore.latestSnapshot(tenant)
            samples = () if snapshot is None else snapshot.toSamples()
        return self.health.evaluate(
            tenant, samples, self.alertStore.listActiveAlerts(tenant), now=self._now()
        )

    # ------------------------------------------------------------------
    # Reads and retention
    # ------------------------------------------------------------------
    def latestSnapshot(self, tenantId: uuid.UUID | str) -> AIMetricSnapshot | None:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        return self.snapshotStore.latestSnapshot(tenant)

    def listSnapshots(
        self,
        tenantId: uuid.UUID | str,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> tuple[AIMetricSnapshot, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        self._requireEnabled()
        return self.snapshotStore.listSnapshots(tenant, since=since, until=until, limit=limit)

    def purgeObservabilityRetention(
        self,
        tenantId: uuid.UUID | str | None = None,
        *,
        snapshotDays: int | None = None,
        alertDays: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        self._requireEnabled()
        tenant = None if tenantId is None else requireUuid(tenantId, "tenantId")
        moment = now or self._now()
        snapshotHorizon = (
            self.settings.snapshotRetentionDays if snapshotDays is None else int(snapshotDays)
        )
        alertHorizon = self.settings.alertRetentionDays if alertDays is None else int(alertDays)
        if snapshotHorizon < 1 or alertHorizon < 1:
            raise AIConfigurationError("Observability retention must be at least one day.")
        return {
            "snapshots": self.snapshotStore.deleteSnapshotsBefore(
                tenant, moment - timedelta(days=snapshotHorizon)
            ),
            "alerts": self.alertStore.deleteAlertsBefore(
                tenant, moment - timedelta(days=alertHorizon)
            ),
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _runAlerting(
        self,
        tenant: uuid.UUID,
        samples: Sequence[MetricSample],
        snapshot: AIMetricSnapshot | None,
        *,
        rules: Sequence[AlertRule] | None = None,
        snapshotId: uuid.UUID | None = None,
    ) -> AlertEvaluation:
        chosen = tuple(rules) if rules is not None else self.alertRules()
        openEvents = self.alertStore.listActiveAlerts(tenant)
        sampleCount = 0
        for sample in samples:
            if sample.name == "aiRequestsTotal" and not sample.labels:
                sampleCount = int(sample.value)
        evaluation = self.evaluator.evaluate(
            chosen,
            samples,
            openEvents,
            tenantId=tenant,
            snapshotId=snapshot.id if snapshot is not None else snapshotId,
            sampleCount=sampleCount,
            now=self._now(),
        )
        for event in evaluation.opened:
            stored = self.alertStore.saveAlert(event)
            self._audit(
                tenant,
                AUDIT_ALERT_FIRED,
                outcome="DENIED" if stored.severity == "CRITICAL" else "RECORDED",
                contextSources=(stored.ruleCode,),
                detail={
                    "alertId": str(stored.id),
                    "metric": stored.metric,
                    "observed": stored.observedValue,
                    "threshold": stored.threshold,
                    "severity": stored.severity,
                },
            )
        for event in evaluation.resolved:
            stored = self.alertStore.updateAlert(event)
            self._audit(
                tenant,
                AUDIT_ALERT_RESOLVED,
                outcome="UPDATED",
                contextSources=(stored.ruleCode,),
                detail={
                    "alertId": str(stored.id),
                    "metric": stored.metric,
                    "durationSeconds": stored.durationSeconds(now=self._now()),
                },
            )
        return evaluation

    def _requireAlert(self, tenant: uuid.UUID, alertId: uuid.UUID | str) -> AIAlertEvent:
        self._requireEnabled()
        alert = self.alertStore.getAlert(tenant, requireUuid(alertId, "alertId"))
        if alert is None or alert.tenantId != tenant:
            raise AIAlertNotFound(str(alertId))
        return alert

    def _requireEnabled(self) -> None:
        if not self.settings.enabled:
            raise AIConfigurationError("The AI observability platform is disabled.")

    def _audit(self, tenant: uuid.UUID, action: str, **kwargs: Any) -> None:
        if self.auditLogger is None:
            return
        self.auditLogger.logAudit(tenant, action, **kwargs)


# ---------------------------------------------------------------------------
# Contributors: thin adapters over the services that already hold the facts.
# Each one is duck-typed against the real service so W imports no sub-phase.
# ---------------------------------------------------------------------------
class UsageMetricsContributor:
    """Phase 13-N: attempts, failures, tokens, cost, latency (§34)."""

    def __init__(self, usageService: Any) -> None:
        self.usageService = usageService
        self.latencies: tuple[float, ...] = ()

    def name(self) -> str:
        return "USAGE"

    def collect(self, tenantId: Any, window: Any) -> tuple[MetricSample, ...]:
        summary = self.usageService.usageSummary(tenantId)
        latency = getattr(summary, "latency", None)
        moment = getattr(window, "end", None)
        attempts = float(getattr(summary, "attempts", 0) or 0)
        failed = float(getattr(summary, "failed", 0) or 0)
        samples = [
            MetricSample(name="aiRequestsTotal", value=attempts, at=moment),
            MetricSample(name="aiRequestsFailed", value=failed, at=moment),
            MetricSample(
                name="aiTokensTotal",
                value=float(getattr(summary, "totalTokens", 0) or 0),
                at=moment,
            ),
            MetricSample(
                name="aiCostTotal",
                value=float(getattr(summary, "costAmount", 0) or 0),
                at=moment,
            ),
            MetricSample(name="aiErrorRatio", value=ratio(failed, attempts), at=moment),
        ]
        if latency is not None:
            samples.append(
                MetricSample(
                    name="aiLatencyAverage",
                    value=float(getattr(latency, "averageMs", 0) or 0),
                    at=moment,
                )
            )
            samples.append(
                MetricSample(
                    name="aiLatencyP95",
                    value=float(getattr(latency, "p95Ms", 0) or 0),
                    at=moment,
                )
            )
        for breakdown in getattr(summary, "byProvider", ()) or ():
            failures = float(getattr(breakdown, "failed", 0) or 0)
            if failures:
                samples.append(
                    MetricSample(
                        name="aiProviderFailures",
                        value=failures,
                        labels={"provider": str(getattr(breakdown, "key", ""))},
                        at=moment,
                    )
                )
        for breakdown in getattr(summary, "byModel", ()) or ():
            failures = float(getattr(breakdown, "failed", 0) or 0)
            if failures:
                samples.append(
                    MetricSample(
                        name="aiModelFailures",
                        value=failures,
                        labels={"model": str(getattr(breakdown, "key", ""))},
                        at=moment,
                    )
                )
        return tuple(samples)


class QueueMetricsContributor:
    """Phase 13-P: how much work is waiting and how much died."""

    def __init__(self, queueService: Any) -> None:
        self.queueService = queueService

    def name(self) -> str:
        return "QUEUE"

    def collect(self, tenantId: Any, window: Any) -> tuple[MetricSample, ...]:
        jobs = self.queueService.listJobs(tenantId)
        moment = getattr(window, "end", None)
        pending = sum(1 for job in jobs if getattr(job, "status", "") == "PENDING")
        failed = sum(1 for job in jobs if getattr(job, "status", "") in ("FAILED", "DEAD"))
        return (
            MetricSample(name="aiQueueDepth", value=float(pending), at=moment),
            MetricSample(name="aiJobsFailed", value=float(failed), at=moment),
        )


class EvaluationMetricsContributor:
    """Phase 13-U: the latest run's score and failing cases."""

    def __init__(self, evaluationService: Any, *, suiteCode: str = "") -> None:
        self.evaluationService = evaluationService
        self.suiteCode = suiteCode

    def name(self) -> str:
        return "EVALUATION"

    def collect(self, tenantId: Any, window: Any) -> tuple[MetricSample, ...]:
        runs = self.evaluationService.listRuns(tenantId, self.suiteCode, limit=1)
        if not runs:
            return ()
        run = runs[0]
        moment = getattr(window, "end", None)
        return (
            MetricSample(
                name="aiEvaluationScore",
                value=float(getattr(run, "overallScore", 0.0) or 0.0),
                at=moment,
            ),
            MetricSample(
                name="aiEvaluationFailures",
                value=float(getattr(run, "failedCount", 0) or 0),
                at=moment,
            ),
        )


class FeedbackMetricsContributor:
    """Phase 13-V: how satisfied the humans are (§34 feedbackScore)."""

    def __init__(self, feedbackService: Any) -> None:
        self.feedbackService = feedbackService

    def name(self) -> str:
        return "FEEDBACK"

    def collect(self, tenantId: Any, window: Any) -> tuple[MetricSample, ...]:
        summary = self.feedbackService.summarize(
            tenantId,
            since=getattr(window, "start", None),
            until=getattr(window, "end", None),
        )
        if getattr(summary, "isEmpty", True):
            return ()
        return (
            MetricSample(
                name="aiFeedbackScore",
                value=float(getattr(summary, "satisfaction", 0.0) or 0.0),
                at=getattr(window, "end", None),
            ),
        )


class MetricsCollectionJobHandler:
    """Phase 13-P handler for the ``MONITORING`` job kind (§W.12).

    Payload contract::

        {"windowMinutes": 60, "evaluateAlerts": true, "purge": false}
    """

    JOB_KIND = "MONITORING"

    def __init__(self, service: ObservabilityApplicationService) -> None:
        self.service = service

    def kind(self) -> str:
        return self.JOB_KIND

    def execute(self, job: Any) -> Any:
        from apps.ai.domain.services.jobQueue import JobOutcome

        payload = dict(getattr(job, "payload", {}) or {})
        rawMinutes = payload.get("windowMinutes")
        window = None
        if rawMinutes is not None:
            try:
                minutes = int(rawMinutes)
            except (TypeError, ValueError) as error:
                raise AIObservabilityWindowInvalid("windowMinutes must be an integer.") from error
            end = self.service._now()  # noqa: SLF001 - the service owns the clock
            window = MetricWindow(start=end - timedelta(minutes=minutes), end=end)
        result = self.service.collect(
            job.tenantId,
            window=window,
            evaluateAlerts=bool(payload.get("evaluateAlerts", True)),
        )
        purged: dict[str, int] = {}
        if bool(payload.get("purge", False)):
            purged = self.service.purgeObservabilityRetention(job.tenantId)
        return JobOutcome(
            outcome="SUCCEEDED",
            summary={
                "snapshotId": str(result.snapshot.id),
                "metrics": len(result.snapshot.metrics),
                "opened": len(result.openedAlerts),
                "resolved": len(result.resolvedAlerts),
                "failedSources": [name for name, _ in result.failedSources],
                "purged": purged,
            },
        )


__all__ = [
    "AUDIT_ALERT_ACKNOWLEDGED",
    "AUDIT_ALERT_FIRED",
    "AUDIT_ALERT_RESOLVED",
    "AlertDescriptor",
    "CollectionResult",
    "EvaluationMetricsContributor",
    "FeedbackMetricsContributor",
    "MetricsCollectionJobHandler",
    "ObservabilityApplicationService",
    "ObservabilitySettings",
    "QueueMetricsContributor",
    "UsageMetricsContributor",
]
