"""Observability entities for Phase 13-W.

Two records make the platform's behaviour inspectable over time:

- ``AIMetricSnapshot`` — the metrics of one collection window, frozen so
  "what did last Tuesday look like?" survives the retention of the raw
  rows it was derived from;
- ``AIAlertEvent`` — one firing of one rule, with its own lifecycle
  (``FIRING → RESOLVED`` / ``ACKNOWLEDGED``). Alerts are events, not
  flags: a rule that fires, resolves, and fires again leaves three rows,
  which is what makes "how often does this break?" answerable.

Pure dataclasses: no Django, ORM, HTTP, provider SDK, queue, or network
dependency.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from apps.ai.domain.entities.aiRecords import newId, requireUuid, utcNow
from apps.ai.domain.valueObjects.observabilityTypes import (
    MetricSample,
    coerceValue,
    ensureAlertSeverity,
    ensureAlertState,
    ensureHealthStatus,
    ensureMetricName,
    sanitizeLabels,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

#: Alert lifecycle. ``RESOLVED`` and ``ACKNOWLEDGED`` are terminal for the
#: event; the next breach opens a new one (§W.8).
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "FIRING": {"RESOLVED", "ACKNOWLEDGED"},
    "ACKNOWLEDGED": {"RESOLVED"},
    "RESOLVED": set(),
    "OK": {"FIRING"},
}

_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,79}$")


def ensureRuleCode(value: str) -> str:
    normalized = str(value or "").strip().upper().replace(" ", "_")
    if not _CODE_PATTERN.fullmatch(normalized):
        raise ValidationFailedError(
            "Alert rule code must be an uppercase identifier.",
            fieldErrors={"ruleCode": normalized[:40]},
        )
    return normalized


@dataclass
class AIMetricSnapshot:
    """The metrics of one collection window (§W.6)."""

    tenantId: uuid.UUID
    windowStart: datetime
    windowEnd: datetime
    metrics: dict[str, float] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    sampleCount: int = 0
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        if not isinstance(self.windowStart, datetime) or not isinstance(self.windowEnd, datetime):
            raise ValidationFailedError("Snapshot window bounds must be datetimes.")
        if self.windowEnd <= self.windowStart:
            raise ValidationFailedError("Snapshot window must end after it starts.")
        if not isinstance(self.metrics, dict):
            raise ValidationFailedError("Snapshot metrics must be a mapping.")
        self.metrics = {
            ensureMetricName(name): coerceValue(value) for name, value in self.metrics.items()
        }
        self.labels = sanitizeLabels(self.labels)
        if not isinstance(self.sampleCount, int) or isinstance(self.sampleCount, bool):
            raise ValidationFailedError("Snapshot sampleCount must be an integer.")
        if self.sampleCount < 0:
            raise ValidationFailedError("Snapshot sampleCount cannot be negative.")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Snapshot metadata must be a mapping.")

    @property
    def durationSeconds(self) -> float:
        return round((self.windowEnd - self.windowStart).total_seconds(), 3)

    def valueFor(self, metric: str, default: float = 0.0) -> float:
        return self.metrics.get(ensureMetricName(metric), default)

    def toSamples(self, *, at: datetime | None = None) -> tuple[MetricSample, ...]:
        moment = at or self.windowEnd
        return tuple(
            MetricSample(name=name, value=value, labels=dict(self.labels), at=moment)
            for name, value in sorted(self.metrics.items())
        )


@dataclass
class AIAlertEvent:
    """One firing of one alert rule (§W.8)."""

    tenantId: uuid.UUID
    ruleCode: str
    metric: str
    severity: str = "WARNING"
    state: str = "FIRING"
    observedValue: float = 0.0
    threshold: float = 0.0
    message: str = ""
    firedAt: datetime = field(default_factory=utcNow)
    resolvedAt: datetime | None = None
    acknowledgedAt: datetime | None = None
    acknowledgedBy: uuid.UUID | None = None
    snapshotId: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.ruleCode = ensureRuleCode(self.ruleCode)
        self.metric = ensureMetricName(self.metric)
        self.severity = ensureAlertSeverity(self.severity)
        self.state = ensureAlertState(self.state)
        self.observedValue = coerceValue(self.observedValue)
        self.threshold = coerceValue(self.threshold)
        self.message = str(self.message or "").strip()[:500]
        if self.snapshotId is not None:
            self.snapshotId = requireUuid(self.snapshotId, "snapshotId")
        if self.acknowledgedBy is not None:
            self.acknowledgedBy = requireUuid(self.acknowledgedBy, "acknowledgedBy")
        if not isinstance(self.metadata, dict):
            raise ValidationFailedError("Alert metadata must be a mapping.")

    @property
    def isActive(self) -> bool:
        return self.state in ("FIRING", "ACKNOWLEDGED")

    @property
    def isTerminal(self) -> bool:
        return self.state == "RESOLVED"

    def transitionTo(self, state: str, *, now: datetime | None = None) -> None:
        target = ensureAlertState(state)
        if target != self.state and target not in _ALLOWED_TRANSITIONS[self.state]:
            raise ValidationFailedError(
                f"Invalid alert transition {self.state} → {target}.",
                fieldErrors={"state": target},
            )
        self.state = target

    def acknowledge(
        self, *, actorId: uuid.UUID | str | None = None, now: datetime | None = None
    ) -> None:
        moment = now or utcNow()
        self.transitionTo("ACKNOWLEDGED", now=moment)
        self.acknowledgedAt = moment
        self.acknowledgedBy = None if actorId is None else requireUuid(actorId, "actorId")

    def resolve(self, *, now: datetime | None = None) -> None:
        moment = now or utcNow()
        self.transitionTo("RESOLVED", now=moment)
        self.resolvedAt = moment

    def durationSeconds(self, *, now: datetime | None = None) -> float:
        end = self.resolvedAt or now or utcNow()
        return max(0.0, round((end - self.firedAt).total_seconds(), 3))


@dataclass(frozen=True)
class ComponentHealth:
    """Health of one platform component with the reason behind it."""

    component: str
    status: str
    reason: str = ""
    metrics: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "component", str(self.component or "").strip().upper())
        object.__setattr__(self, "status", ensureHealthStatus(self.status))
        if not self.component:
            raise ValidationFailedError("Component health requires a component name.")

    @property
    def isHealthy(self) -> bool:
        return self.status == "HEALTHY"


@dataclass(frozen=True)
class HealthReport:
    """Overall platform health, worst component wins (§W.9)."""

    tenantId: uuid.UUID
    status: str
    components: tuple[ComponentHealth, ...] = ()
    activeAlerts: int = 0
    criticalAlerts: int = 0
    evaluatedAt: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", ensureHealthStatus(self.status))

    @property
    def isHealthy(self) -> bool:
        return self.status == "HEALTHY"

    def componentFor(self, component: str) -> ComponentHealth | None:
        wanted = str(component or "").strip().upper()
        for item in self.components:
            if item.component == wanted:
                return item
        return None

    def degradedComponents(self) -> tuple[str, ...]:
        return tuple(item.component for item in self.components if not item.isHealthy)


__all__ = [
    "AIAlertEvent",
    "AIMetricSnapshot",
    "ComponentHealth",
    "HealthReport",
    "ensureRuleCode",
]
