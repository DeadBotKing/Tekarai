"""Django persistence for the Phase 13-W observability platform.

Row↔entity mapping only — no business rule lives here. Every read and
write is tenant-scoped, and entities are rehydrated through the domain
records so an invalid stored row can never re-enter the domain.

``deleteAlertsBefore`` spares alerts that are still active: an outage that
started before the retention horizon must not disappear from the console
while it is still happening.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.db.models import Q

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.observabilityRecords import AIAlertEvent, AIMetricSnapshot
from apps.ai.domain.exceptions import AIAlertRuleInvalid
from apps.ai.infrastructure.models import AIAlertEventModel, AIMetricSnapshotModel


def snapshotToEntity(row: AIMetricSnapshotModel) -> AIMetricSnapshot:
    return AIMetricSnapshot(
        tenantId=row.tenantId,
        windowStart=row.windowStart,
        windowEnd=row.windowEnd,
        metrics={key: float(value) for key, value in (row.metrics or {}).items()},
        labels=dict(row.labels or {}),
        sampleCount=row.sampleCount,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


def alertToEntity(row: AIAlertEventModel) -> AIAlertEvent:
    return AIAlertEvent(
        tenantId=row.tenantId,
        ruleCode=row.ruleCode,
        metric=row.metric,
        severity=row.severity,
        state=row.state,
        observedValue=float(row.observedValue),
        threshold=float(row.threshold),
        message=row.message or "",
        firedAt=row.firedAt,
        resolvedAt=row.resolvedAt,
        acknowledgedAt=row.acknowledgedAt,
        acknowledgedBy=row.acknowledgedBy,
        snapshotId=row.snapshotId,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


class DjangoMetricSnapshotStore:
    """``MetricSnapshotStore`` over ``aiMetricSnapshots``."""

    def saveSnapshot(self, snapshot: AIMetricSnapshot) -> AIMetricSnapshot:
        row = AIMetricSnapshotModel.objects.create(
            id=snapshot.id,
            tenantId=snapshot.tenantId,
            windowStart=snapshot.windowStart,
            windowEnd=snapshot.windowEnd,
            metrics=dict(snapshot.metrics),
            labels=dict(snapshot.labels),
            sampleCount=snapshot.sampleCount,
            metadata=dict(snapshot.metadata),
        )
        return snapshotToEntity(row)

    def getSnapshot(self, tenantId: uuid.UUID, snapshotId: uuid.UUID) -> AIMetricSnapshot | None:
        row = AIMetricSnapshotModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            id=requireUuid(snapshotId, "snapshotId"),
        ).first()
        return None if row is None else snapshotToEntity(row)

    def latestSnapshot(self, tenantId: uuid.UUID) -> AIMetricSnapshot | None:
        row = (
            AIMetricSnapshotModel.objects.filter(tenantId=requireUuid(tenantId, "tenantId"))
            .order_by("-windowEnd", "-createdAt")
            .first()
        )
        return None if row is None else snapshotToEntity(row)

    def listSnapshots(
        self,
        tenantId: uuid.UUID,
        *,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> tuple[AIMetricSnapshot, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if since is not None:
            query &= Q(windowEnd__gte=since)
        if until is not None:
            query &= Q(windowEnd__lt=until)
        rows = AIMetricSnapshotModel.objects.filter(query).order_by("-windowEnd")[
            : max(1, int(limit))
        ]
        return tuple(snapshotToEntity(row) for row in rows)

    def deleteSnapshotsBefore(self, tenantId: uuid.UUID | None, cutoff: datetime) -> int:
        query = AIMetricSnapshotModel.objects.filter(windowEnd__lt=cutoff)
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        removed, _ = query.delete()
        return int(removed)


class DjangoAlertEventStore:
    """``AlertEventStore`` over ``aiAlertEvents``."""

    def saveAlert(self, alert: AIAlertEvent) -> AIAlertEvent:
        row = AIAlertEventModel.objects.create(
            id=alert.id,
            tenantId=alert.tenantId,
            ruleCode=alert.ruleCode,
            metric=alert.metric,
            severity=alert.severity,
            state=alert.state,
            observedValue=Decimal(str(alert.observedValue)),
            threshold=Decimal(str(alert.threshold)),
            message=alert.message,
            firedAt=alert.firedAt,
            resolvedAt=alert.resolvedAt,
            acknowledgedAt=alert.acknowledgedAt,
            acknowledgedBy=alert.acknowledgedBy,
            snapshotId=alert.snapshotId,
            metadata=dict(alert.metadata),
        )
        return alertToEntity(row)

    def updateAlert(self, alert: AIAlertEvent) -> AIAlertEvent:
        updated = AIAlertEventModel.objects.filter(tenantId=alert.tenantId, id=alert.id).update(
            state=alert.state,
            observedValue=Decimal(str(alert.observedValue)),
            message=alert.message,
            resolvedAt=alert.resolvedAt,
            acknowledgedAt=alert.acknowledgedAt,
            acknowledgedBy=alert.acknowledgedBy,
            metadata=dict(alert.metadata),
        )
        if not updated:
            raise AIAlertRuleInvalid("Alert row was not found for update.")
        return alertToEntity(AIAlertEventModel.objects.get(tenantId=alert.tenantId, id=alert.id))

    def getAlert(self, tenantId: uuid.UUID, alertId: uuid.UUID) -> AIAlertEvent | None:
        row = AIAlertEventModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), id=requireUuid(alertId, "alertId")
        ).first()
        return None if row is None else alertToEntity(row)

    def listAlerts(
        self,
        tenantId: uuid.UUID,
        *,
        states: tuple[str, ...] = (),
        severities: tuple[str, ...] = (),
        ruleCode: str = "",
        limit: int = 200,
    ) -> tuple[AIAlertEvent, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if states:
            query &= Q(state__in=[str(value).strip().upper() for value in states])
        if severities:
            query &= Q(severity__in=[str(value).strip().upper() for value in severities])
        if ruleCode:
            query &= Q(ruleCode=str(ruleCode).strip().upper())
        rows = AIAlertEventModel.objects.filter(query).order_by("-firedAt", "-createdAt")[
            : max(1, int(limit))
        ]
        return tuple(alertToEntity(row) for row in rows)

    def listActiveAlerts(self, tenantId: uuid.UUID) -> tuple[AIAlertEvent, ...]:
        rows = AIAlertEventModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            state__in=("FIRING", "ACKNOWLEDGED"),
        ).order_by("firedAt")
        return tuple(alertToEntity(row) for row in rows)

    def deleteAlertsBefore(self, tenantId: uuid.UUID | None, cutoff: datetime) -> int:
        """Purge settled alerts only; a live outage never disappears."""

        query = AIAlertEventModel.objects.filter(firedAt__lt=cutoff, state="RESOLVED")
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        removed, _ = query.delete()
        return int(removed)


__all__ = [
    "DjangoAlertEventStore",
    "DjangoMetricSnapshotStore",
    "alertToEntity",
    "snapshotToEntity",
]
