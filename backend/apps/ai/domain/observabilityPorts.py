"""Observability port interfaces for Phase 13-W.

Minimal contracts the application layer depends on:

- ``MetricContributor`` — anything that can report samples for a window.
  This is the extension point of W: N, P, S, U and V are wired in as
  contributors at the composition root, and a future sub-phase adds one
  more without touching the collector;
- ``MetricSnapshotStore`` / ``AlertEventStore`` — persistence of frozen
  windows and of alert events;
- ``ObservabilityAuditLogger`` — the single Phase 13-O ledger append.

``datetime`` and ``uuid`` are typing-only; the module has no Django, ORM,
HTTP, provider SDK, Redis, queue, or network dependency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from apps.ai.domain.entities.observabilityRecords import AIAlertEvent, AIMetricSnapshot


class MetricContributor(Protocol):
    """One source of metrics for one tenant and one window."""

    def name(self) -> str: ...
    def collect(self, tenantId: Any, window: Any) -> Any: ...


class MetricSnapshotStore(Protocol):
    """Persistence contract for frozen collection windows."""

    def saveSnapshot(self, snapshot: AIMetricSnapshot) -> AIMetricSnapshot: ...
    def getSnapshot(self, tenantId: UUID, snapshotId: UUID) -> AIMetricSnapshot | None: ...
    def latestSnapshot(self, tenantId: UUID) -> AIMetricSnapshot | None: ...
    def listSnapshots(
        self,
        tenantId: UUID,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> tuple[AIMetricSnapshot, ...]: ...
    def deleteSnapshotsBefore(self, tenantId: UUID | None, cutoff: datetime) -> int: ...


class AlertEventStore(Protocol):
    """Persistence contract for alert events."""

    def saveAlert(self, alert: AIAlertEvent) -> AIAlertEvent: ...
    def updateAlert(self, alert: AIAlertEvent) -> AIAlertEvent: ...
    def getAlert(self, tenantId: UUID, alertId: UUID) -> AIAlertEvent | None: ...
    def listAlerts(
        self,
        tenantId: UUID,
        *,
        states: tuple[str, ...] = (),
        severities: tuple[str, ...] = (),
        ruleCode: str = "",
        limit: int = 200,
    ) -> tuple[AIAlertEvent, ...]: ...
    def listActiveAlerts(self, tenantId: UUID) -> tuple[AIAlertEvent, ...]: ...
    def deleteAlertsBefore(self, tenantId: UUID | None, cutoff: datetime) -> int: ...


class ObservabilityAuditLogger(Protocol):
    """The single Phase 13-O entry point W needs (one ledger append)."""

    def logAudit(
        self,
        tenantId: Any,
        action: str,
        *,
        outcome: str = ...,
        actorId: Any = ...,
        contextSources: tuple[str, ...] | list[str] | None = ...,
        detail: dict[str, Any] | None = ...,
    ) -> Any: ...


__all__ = [
    "AlertEventStore",
    "MetricContributor",
    "MetricSnapshotStore",
    "ObservabilityAuditLogger",
]
