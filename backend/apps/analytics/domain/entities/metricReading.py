"""Immutable MetricReading analytical fact."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Any

from apps.analytics.domain.valueObjects.metricTypes import (
    ensureUtc,
    normalizeDimensions,
    normalizeIngestionKey,
    normalizeMetricValue,
    normalizeQuality,
)
from apps.sharedKernel.domain.entities import newId
from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.events import DomainEvent


@dataclass(frozen=True, slots=True)
class MetricReading:
    """One append-only metric value for a bounded UTC period.

    ``periodStart == periodEnd`` represents an instantaneous observation.
    Dataclass freezing makes accidental domain mutation fail immediately; the
    persistence model independently rejects updates and instance deletes.
    """

    id: uuid.UUID
    tenantId: uuid.UUID
    metricId: uuid.UUID
    value: Decimal
    periodStart: datetime
    periodEnd: datetime
    dimensions: Mapping[str, str | int | float | bool | None]
    quality: str
    sourceType: str
    sourceId: str
    ingestionKey: str
    recordedAt: datetime
    recordedById: uuid.UUID | None = None
    correlationId: str = ""

    def __post_init__(self) -> None:
        # Freeze the nested mapping as well as the dataclass itself; otherwise
        # callers could mutate a reading through ``dimensions[...]=...``.
        object.__setattr__(self, "dimensions", MappingProxyType(dict(self.dimensions)))

    @staticmethod
    def record(
        *,
        tenantId: uuid.UUID,
        metricId: uuid.UUID,
        value: object,
        periodStart: datetime,
        periodEnd: datetime,
        dimensions: object,
        quality: str,
        sourceType: str,
        sourceId: str,
        ingestionKey: str,
        recordedAt: datetime,
        recordedById: uuid.UUID | None,
        correlationId: str,
    ) -> MetricReading:
        start = ensureUtc(periodStart, "periodStart")
        end = ensureUtc(periodEnd, "periodEnd")
        if end < start:
            raise ValidationFailedError(
                "Metric period end cannot precede its start.",
                fieldErrors={"periodEnd": "must be >= periodStart"},
            )
        normalizedSourceType = str(sourceType or "").strip()
        normalizedSourceId = str(sourceId or "").strip()
        if len(normalizedSourceType) > 64:
            raise ValidationFailedError(
                "Source type is too long.", fieldErrors={"sourceType": "maximum 64"}
            )
        if len(normalizedSourceId) > 128:
            raise ValidationFailedError(
                "Source identifier is too long.", fieldErrors={"sourceId": "maximum 128"}
            )
        if bool(normalizedSourceType) != bool(normalizedSourceId):
            raise ValidationFailedError(
                "Source type and source identifier must be supplied together.",
                fieldErrors={"sourceId": "sourceType/sourceId pair required"},
            )
        return MetricReading(
            id=newId(),
            tenantId=tenantId,
            metricId=metricId,
            value=normalizeMetricValue(value),
            periodStart=start,
            periodEnd=end,
            dimensions=MappingProxyType(normalizeDimensions(dimensions)),
            quality=normalizeQuality(quality),
            sourceType=normalizedSourceType,
            sourceId=normalizedSourceId,
            ingestionKey=normalizeIngestionKey(ingestionKey),
            recordedAt=ensureUtc(recordedAt, "recordedAt"),
            recordedById=recordedById,
            correlationId=str(correlationId or "")[:64],
        )

    def sameObservationAs(self, other: MetricReading) -> bool:
        """Payload equality used by durable idempotency conflict detection."""

        return (
            self.tenantId == other.tenantId
            and self.metricId == other.metricId
            and self.value == other.value
            and self.periodStart == other.periodStart
            and self.periodEnd == other.periodEnd
            and self.dimensions == other.dimensions
            and self.quality == other.quality
            and self.sourceType == other.sourceType
            and self.sourceId == other.sourceId
        )

    def recordedEvent(self) -> DomainEvent:
        return DomainEvent(
            name="metricReadingRecorded",
            occurredAt=self.recordedAt,
            tenantId=self.tenantId,
            actorId=self.recordedById,
            correlationId=self.correlationId,
            payload={
                "readingId": str(self.id),
                "metricId": str(self.metricId),
                "periodStart": self.periodStart.isoformat(),
                "periodEnd": self.periodEnd.isoformat(),
                "quality": self.quality,
                "sourceType": self.sourceType,
                "sourceId": self.sourceId,
            },
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "metricId": str(self.metricId),
            "value": str(self.value),
            "periodStart": self.periodStart.isoformat(),
            "periodEnd": self.periodEnd.isoformat(),
            "dimensions": dict(self.dimensions),
            "quality": self.quality,
            "sourceType": self.sourceType,
            "sourceId": self.sourceId,
            "ingestionKey": self.ingestionKey,
            "recordedAt": self.recordedAt.isoformat(),
        }
